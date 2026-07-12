from fastapi import FastAPI

from app.api.media import router as media_router
from app.api.sessions import router as sessions_router

app = FastAPI(title="Repair Logic Agent")
app.include_router(media_router)
app.include_router(sessions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
