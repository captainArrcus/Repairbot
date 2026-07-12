from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.media import router as media_router
from app.api.sessions import router as sessions_router

app = FastAPI(title="Repair Logic Agent")
# ponytail: allow-all CORS for the Feature 1.4 web prototype (page :8080 → API :8000);
# tighten to real origins when auth lands (Feature 2.5) / prod deploy (3.1)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(media_router)
app.include_router(sessions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
