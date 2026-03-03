from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from database import SessionLocal, Resume, EmailDraft
from groq import Groq
import pdfplumber, os, uuid, io

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def extract_text_from_pdf(file_bytes):
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def generate_email(resume_text, job_description):
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

@app.post("/generate")
async def generate(
    resume: UploadFile = File(...),
    job_description: str = Form(...)
):
    db = SessionLocal()
    try:
        file_bytes = await resume.read()
        resume_text = extract_text_from_pdf(file_bytes)
        email = generate_email(resume_text, job_description)
        resume_id = str(uuid.uuid4())
        draft_id = str(uuid.uuid4())
        db.add(Resume(id=resume_id, filename=resume.filename, extracted_text=resume_text))
        db.add(EmailDraft(id=draft_id, job_description=job_description, generated_email=email))
        db.commit()
        return {"email": email, "resume_id": resume_id}
    finally:
        db.close()

@app.get("/history", response_class=HTMLResponse)
def history():
    db = SessionLocal()
    drafts = db.query(EmailDraft).order_by(EmailDraft.created_at.desc()).all()
    db.close()
    rows = "".join(f"<tr><td style='padding:12px'>{d.generated_email[:100]}...</td><td style='padding:12px'>{d.created_at.strftime('%b %d, %Y')}</td></tr>" for d in drafts)
    return f"<html><body style='font-family:sans-serif; padding:40px'><h2>Past Emails</h2><table width='100%'><tr><th>Email Preview</th><th>Date</th></tr>{rows}</table><br><a href='/'>Back</a></body></html>"
