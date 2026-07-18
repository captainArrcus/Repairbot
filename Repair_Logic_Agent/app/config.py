import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/repair")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "repair-media")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# direct litellm call in dev (like the knowledge spikes); LiteLLM proxy lands with the
# 3.1 deploy (spec 2.5 D11 — env swap by design)
VISION_MODEL = os.getenv("VISION_MODEL", "gemini/gemini-2.5-flash")
# Techstack STT: large-v3 in production; CPU dev boxes override in .env (base), tests use tiny
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "de")

# --- Feature 2.5: embedded hermes agent ---
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# scripted = deterministic Wizard-of-Oz engine (CI, golden harness); hermes = real agent
AGENT_BACKEND = os.getenv("AGENT_BACKEND", "scripted")
# worker command (subprocess runner); tests point this at the stub worker
AGENT_WORKER_CMD = os.getenv(
    "AGENT_WORKER_CMD",
    f"{_REPO_ROOT}/.venv-hermes/bin/python {_REPO_ROOT}/Repair_Logic_Agent/agents/hermes_worker.py",
)
# subprocess (dev/test) | docker (egress-isolated worker container, spec 2.5 D8)
AGENT_RUNNER = os.getenv("AGENT_RUNNER", "subprocess")
AGENT_DOCKER_IMAGE = os.getenv("AGENT_DOCKER_IMAGE", "repair-agent-worker")
AGENT_DOCKER_NETWORK = os.getenv("AGENT_DOCKER_NETWORK", "repair-agent_internal")
AGENT_EGRESS_PROXY = os.getenv("AGENT_EGRESS_PROXY", "http://egress-proxy:3128")
AGENT_TURN_TIMEOUT_S = float(os.getenv("AGENT_TURN_TIMEOUT_S", "180"))
HERMES_HOME_ROOT = os.getenv(
    "HERMES_HOME_ROOT", f"{_REPO_ROOT}/Repair_Logic_Agent/agents/.hermes_home"
)
REPAIR_LLM_BASE_URL = os.getenv(
    "REPAIR_LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
REPAIR_LLM_MODEL = os.getenv("REPAIR_LLM_MODEL", "gemini-3.1-flash-lite")
REPAIR_LLM_API_KEY = os.getenv("REPAIR_LLM_API_KEY") or GOOGLE_API_KEY
REPAIR_LLM_FALLBACK_MODEL = os.getenv("REPAIR_LLM_FALLBACK_MODEL")
