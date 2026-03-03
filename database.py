from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os, datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(String, primary_key=True)
    filename = Column(String)
    extracted_text = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EmailDraft(Base):
    __tablename__ = "email_drafts"
    id = Column(String, primary_key=True)
    job_description = Column(Text)
    generated_email = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(engine)