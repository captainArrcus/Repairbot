import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/repair")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "repair-media")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# direct litellm call in dev (like the knowledge spikes); proxy endpoint comes with 2.5
VISION_MODEL = os.getenv("VISION_MODEL", "gemini/gemini-2.5-flash")
# Techstack STT: large-v3 in production; CPU dev boxes override in .env (base), tests use tiny
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "de")
