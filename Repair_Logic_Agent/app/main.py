from fastapi import FastAPI

from app.api.media import router as media_router

app = FastAPI(title="Repair Logic Agent")
app.include_router(media_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
