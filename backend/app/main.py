from fastapi import FastAPI

app = FastAPI(title="youn-server")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
