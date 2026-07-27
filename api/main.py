from fastapi import FastAPI

app = FastAPI(title="uscode-redesign")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
