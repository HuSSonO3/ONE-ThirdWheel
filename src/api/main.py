from fastapi import FastAPI

app = FastAPI(title="Company Chat API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
