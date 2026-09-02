from fastapi import FastAPI

from app.api.runs import router as runs_router

app = FastAPI(title="Auth-Logic Hunter")
app.include_router(runs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
