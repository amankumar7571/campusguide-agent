"""Configuration for CampusGuide Agent.

Local default is SQLite (no Postgres/Docker on the dev machine).
Set DATABASE_URL to a Postgres URL (see docker-compose.yml) for deployment.
Embeddings: Gemini only when GEMINI_API_KEY is set; otherwise the local
TF-IDF fallback (see embeddings.py). Nothing here invents a hosted service.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load project .env (GEMINI_API_KEY etc.) — config reads os.environ only,
# so without this the .env file is inert.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    pass
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "documents"
DB_PATH = BASE_DIR / "campusguide.db"

DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{DB_PATH}"
)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))

# CORS: comma-separated allowed origins. Default is the local dev
# frontend only — never "*" in production. Deploy sets this to the
# deployed frontend domain, e.g. CORS_ORIGINS=https://campusguide.vercel.app
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173").split(",") if o.strip()]

# Guardrails
MAX_STEPS_PER_REQUEST = int(os.environ.get("MAX_STEPS_PER_REQUEST", "8"))
MAX_TOKENS_PER_REQUEST = int(os.environ.get("MAX_TOKENS_PER_REQUEST", "4000"))
TOP_K = int(os.environ.get("TOP_K", "5"))
RRF_K = 60
RETRIEVAL_MIN_SCORE = float(os.environ.get("RETRIEVAL_MIN_SCORE", "0.05"))

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
