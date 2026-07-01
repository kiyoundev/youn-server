from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.analysis_result import AnalysisResult
from app.models.stock_alert import StockAlert
from app.schemas.analysis_result import AnalysisResultResponse
from app.schemas.stock_alert import StockAlertCreate, StockAlertResponse, StockAlertUpdate
from app.services.stocks import FinnhubClient

router = APIRouter()


@router.get("/api/stocks", response_model=list[StockAlertResponse])
async def list_stock_alerts(db: AsyncSession = Depends(get_db)) -> list[StockAlert]:
    result = await db.execute(select(StockAlert))
    return list(result.scalars().all())


@router.get("/api/stocks/{alert_id}", response_model=StockAlertResponse)
async def get_stock_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> StockAlert:
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")
    return alert


@router.post("/api/stocks", response_model=StockAlertResponse, status_code=201)
async def create_stock_alert(
    body: StockAlertCreate, request: Request, db: AsyncSession = Depends(get_db)
) -> StockAlert:
    finnhub: FinnhubClient = request.app.state.finnhub
    if not await finnhub.validate_ticker(body.ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker")

    alert = StockAlert(
        ticker=body.ticker,
        target_price=body.target_price,
        direction=body.direction,
        run_analysis=body.run_analysis,
    )
    db.add(alert)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="An alert for this ticker and direction already exists"
        )

    finnhub.add_alert(alert)
    return alert


@router.patch("/api/stocks/{alert_id}", response_model=StockAlertResponse)
async def update_stock_alert(
    alert_id: int, body: StockAlertUpdate, request: Request, db: AsyncSession = Depends(get_db)
) -> StockAlert:
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")

    finnhub: FinnhubClient = request.app.state.finnhub
    was_active = alert.active

    if body.target_price is not None:
        alert.target_price = body.target_price
    if body.direction is not None:
        alert.direction = body.direction
    if body.run_analysis is not None:
        alert.run_analysis = body.run_analysis
    if body.active is not None:
        alert.active = body.active

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="An alert for this ticker and direction already exists"
        )

    if body.active is not None and body.active != was_active:
        if alert.active:
            finnhub.add_alert(alert)
        else:
            finnhub.remove_alert(alert.id, alert.ticker)
    elif body.target_price is not None or body.direction is not None:
        finnhub.update_alert(alert)

    return alert


@router.delete("/api/stocks/{alert_id}", status_code=204)
async def delete_stock_alert(
    alert_id: int, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")

    finnhub: FinnhubClient = request.app.state.finnhub
    finnhub.remove_alert(alert.id, alert.ticker)

    await db.delete(alert)
    await db.commit()


@router.post(
    "/api/stocks/{alert_id}/analyze", response_model=AnalysisResultResponse, status_code=201
)
async def analyze_stock_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> AnalysisResult:
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")

    existing = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.ticker == alert.ticker,
            AnalysisResult.status.in_(["pending", "running"]),
        )
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=409, detail="An analysis is already running for this ticker"
        )

    analysis = AnalysisResult(
        stock_alert_id=alert.id,
        ticker=alert.ticker,
        triggered_price=alert.last_price,
        status="pending",
    )
    db.add(analysis)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="An analysis is already running for this ticker"
        )
    return analysis


@router.get("/api/stocks/{alert_id}/analysis", response_model=list[AnalysisResultResponse])
async def list_analysis_results(
    alert_id: int, limit: int = Query(10, ge=1, le=100), db: AsyncSession = Depends(get_db)
) -> list[AnalysisResult]:
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")

    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.stock_alert_id == alert_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
