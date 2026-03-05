from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from database import SessionLocal, Resume, EmailDraft
from groq import Groq
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import pdfplumber, os, uuid, io, base64
from email.mime.text import MIMEText

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY"))
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile https://www.googleapis.com/auth/gmail.send"}
)

def extract_text_from_pdf(file_bytes):
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def generate_email_content(resume_text, job_description):
    prompt = f"You are an expert career coach. Write a short personalized cold email for a job application.\n\nRESUME:\n{resume_text[:3000]}\n\nJOB DESCRIPTION:\n{job_description[:2000]}\n\nWrite ONLY the email with subject line. Keep it under 200 words."
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    return response.choices[0].message.content

@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html") as f:
        return f.read()

@app.get("/auth/google")
async def google_login(request: Request):
    redirect_uri = "http://localhost:8000/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    request.session["user"] = {
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture", ""),
        "access_token": token.get("access_token", "")
    }
    return RedirectResponse(url="/")

@app.get("/me")
def get_user(request: Request):
    user = request.session.get("user")
    if not user:
        return {"logged_in": False}
    return {"logged_in": True, "user": user}

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

@app.post("/generate")
async def generate(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...)
):
    db = SessionLocal()
    try:
        file_bytes = await resume.read()
        resume_text = extract_text_from_pdf(file_bytes)
        email = generate_email_content(resume_text, job_description)
        resume_id = str(uuid.uuid4())
        draft_id = str(uuid.uuid4())
        db.add(Resume(id=resume_id, filename=resume.filename, extracted_text=resume_text))
        db.add(EmailDraft(id=draft_id, job_description=job_description, generated_email=email))
        db.commit()
        return {"email": email, "resume_id": resume_id, "draft_id": draft_id}
    finally:
        db.close()

@app.post("/send-email")
async def send_email(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    data = await request.json()
    recipient = data.get("recipient")
    subject = data.get("subject", "Job Application")
    body = data.get("body")
    if not recipient or not body:
        return JSONResponse({"error": "Missing recipient or body"}, status_code=400)
    try:
        creds = Credentials(token=user["access_token"])
        service = build("gmail", "v1", credentials=creds)
        message = MIMEText(body)
        message["to"] = recipient
        message["subject"] = subject
        message["from"] = user["email"]
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"success": True, "message": "Email sent successfully!"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/history")
def history(request: Request):
    db = SessionLocal()
    drafts = db.query(EmailDraft).order_by(EmailDraft.created_at.desc()).all()
    db.close()
    return {"drafts": [{"email": d.generated_email, "date": d.created_at.strftime("%b %d, %Y"), "job": d.job_description[:60]} for d in drafts]}
