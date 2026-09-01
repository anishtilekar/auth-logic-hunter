from fastapi import FastAPI

app = FastAPI(title="Auth-Logic Hunter")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
