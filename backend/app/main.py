from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db

app = FastAPI(title="youn-server")


@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    return {"status": "ok"}
