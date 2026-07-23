from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.analysis_result import AnalysisResult
from app.models.stock_alert import StockAlert
from app.schemas.analysis_result import AnalysisResultResponse
from app.schemas.stock_alert import (
    StockAlertCreate,
    StockAlertResponse,
    StockAlertUpdate,
    alert_type_direction_mismatch,
)
from app.services import trading_agents
from app.services.stocks import FinnhubClient

router = APIRouter()


def _analysts_to_csv(analysts: list[str] | None) -> str | None:
    return ",".join(analysts) if analysts is not None else None


@router.get(
    "/api/stocks",
    response_model=list[StockAlertResponse],
    summary="List all stock alerts",
)
async def list_stock_alerts(db: AsyncSession = Depends(get_db)) -> list[StockAlert]:
    """List all tracked stock price alerts.

    Returns:
        Every `StockAlert` row, active and paused alike.
    """
    result = await db.execute(select(StockAlert))
    return list(result.scalars().all())


@router.get(
    "/api/stocks/{alert_id}",
    response_model=StockAlertResponse,
    summary="Get a single stock alert",
)
async def get_stock_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> StockAlert:
    """Fetch one stock alert by ID.

    Args:
        alert_id: Primary key of the `StockAlert` row.

    Returns:
        The matching `StockAlert`.

    Raises:
        HTTPException: 404 if no alert exists with that ID.
    """
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")
    return alert


@router.post(
    "/api/stocks",
    response_model=StockAlertResponse,
    status_code=201,
    summary="Create a new stock alert",
    description="Validates the ticker via Finnhub before saving.",
)
async def create_stock_alert(
    body: StockAlertCreate, request: Request, db: AsyncSession = Depends(get_db)
) -> StockAlert:
    """Create a new stock price alert and subscribe it on the live Finnhub feed.

    Args:
        body: New alert fields — ticker, target price, direction, alert type,
            optional TradingAgents run config.

    Returns:
        The newly created `StockAlert`.

    Raises:
        HTTPException: 400 if the ticker fails Finnhub validation.
        HTTPException: 409 if an alert with the same ticker/direction/alert_type
            combination already exists.
    """
    finnhub: FinnhubClient = request.app.state.finnhub
    if not await finnhub.validate_ticker(body.ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker")

    alert = StockAlert(
        ticker=body.ticker,
        target_price=body.target_price,
        direction=body.direction,
        alert_type=body.alert_type,
        run_analysis=body.run_analysis,
        deep_think_llm=body.deep_think_llm,
        quick_think_llm=body.quick_think_llm,
        anthropic_effort=body.anthropic_effort,
        max_debate_rounds=body.max_debate_rounds,
        max_risk_discuss_rounds=body.max_risk_discuss_rounds,
        analysts=_analysts_to_csv(body.analysts),
    )
    db.add(alert)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An alert for this ticker, direction, and alert_type already exists",
        )

    finnhub.add_alert(alert)
    return alert


@router.patch(
    "/api/stocks/{alert_id}",
    response_model=StockAlertResponse,
    summary="Update a stock alert",
    description=(
        "Partial update — omitted fields are left unchanged. Nullable "
        "TradingAgents config fields (deep_think_llm, quick_think_llm, "
        "anthropic_effort, max_debate_rounds, max_risk_discuss_rounds, analysts) "
        "can be explicitly set back to `null` to revert to the global default."
    ),
)
async def update_stock_alert(
    alert_id: int, body: StockAlertUpdate, request: Request, db: AsyncSession = Depends(get_db)
) -> StockAlert:
    """Update a stock alert's thresholds, run config, or active status.

    Re-subscribes/unsubscribes/updates the live Finnhub feed to match the
    resulting `active` state.

    Args:
        alert_id: Primary key of the `StockAlert` row.
        body: Fields to change; any field omitted from the request body is
            left untouched.

    Returns:
        The updated `StockAlert`.

    Raises:
        HTTPException: 404 if no alert exists with that ID.
        HTTPException: 422 if the merged direction/alert_type combination is
            invalid (`stop_loss` requires `direction='below'`; `take_profit`
            requires `direction='above'`).
        HTTPException: 409 if the update collides with another alert's
            ticker/direction/alert_type combination.
    """
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")

    finnhub: FinnhubClient = request.app.state.finnhub
    was_active = alert.active

    if body.target_price is not None:
        alert.target_price = body.target_price
    if body.direction is not None:
        alert.direction = body.direction
    if body.alert_type is not None:
        alert.alert_type = body.alert_type
    if body.run_analysis is not None:
        alert.run_analysis = body.run_analysis
    if body.active is not None:
        alert.active = body.active

    # These are nullable and independently settable back to null (to revert to the
    # global default), so use fields_set rather than "is not None" — an omitted
    # field must be left alone, but an explicit `null` must actually clear it.
    fields_set = body.model_fields_set
    if "deep_think_llm" in fields_set:
        alert.deep_think_llm = body.deep_think_llm
    if "quick_think_llm" in fields_set:
        alert.quick_think_llm = body.quick_think_llm
    if "anthropic_effort" in fields_set:
        alert.anthropic_effort = body.anthropic_effort
    if "max_debate_rounds" in fields_set:
        alert.max_debate_rounds = body.max_debate_rounds
    if "max_risk_discuss_rounds" in fields_set:
        alert.max_risk_discuss_rounds = body.max_risk_discuss_rounds
    if "analysts" in fields_set:
        alert.analysts = _analysts_to_csv(body.analysts)

    # StockAlertUpdate only validates direction/alert_type against each other when
    # both are set in the same request. A PATCH that changes only one of the two
    # against an existing alert's other field (e.g. alert_type=take_profit alone
    # on an existing direction="below" alert) must be checked against the merged
    # state here.
    if alert_type_direction_mismatch(alert.direction, alert.alert_type):
        raise HTTPException(
            status_code=422,
            detail="stop_loss requires direction='below'; take_profit requires direction='above'",
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An alert for this ticker, direction, and alert_type already exists",
        )

    if body.active is not None and body.active != was_active:
        if alert.active:
            finnhub.add_alert(alert)
        else:
            finnhub.remove_alert(alert.id, alert.ticker)
    elif body.target_price is not None or body.direction is not None or body.alert_type is not None:
        finnhub.update_alert(alert)

    return alert


@router.delete(
    "/api/stocks/{alert_id}",
    status_code=204,
    summary="Delete a stock alert",
    description="Also unsubscribes the ticker from the live Finnhub feed.",
)
async def delete_stock_alert(
    alert_id: int, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    """Delete a stock alert and unsubscribe it from the live feed.

    Args:
        alert_id: Primary key of the `StockAlert` row.

    Raises:
        HTTPException: 404 if no alert exists with that ID.
    """
    alert = await db.get(StockAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Stock alert not found")

    finnhub: FinnhubClient = request.app.state.finnhub
    finnhub.remove_alert(alert.id, alert.ticker)

    await db.delete(alert)
    await db.commit()


@router.post(
    "/api/stocks/{alert_id}/analyze",
    response_model=AnalysisResultResponse,
    status_code=201,
    summary="Manually trigger a TradingAgents analysis",
    description=(
        "Ignores the alert's own `run_analysis` flag and always runs. "
        "Spawns the TradingAgents subprocess as a background task and returns "
        "immediately with `status='pending'` — poll "
        "`GET /api/stocks/{alert_id}/analysis` for progress/results."
    ),
)
async def analyze_stock_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> AnalysisResult:
    """Manually trigger a TradingAgents analysis run for a stock alert.

    Args:
        alert_id: Primary key of the `StockAlert` row.

    Returns:
        The newly created `AnalysisResult`, with `status='pending'`.

    Raises:
        HTTPException: 404 if no alert exists with that ID.
        HTTPException: 409 if an analysis for this ticker is already
            `pending` or `running`.
    """
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

    trading_agents.spawn(trading_agents.run_analysis(alert, analysis.id))
    return analysis


@router.get(
    "/api/stocks/{alert_id}/analysis",
    response_model=list[AnalysisResultResponse],
    summary="List TradingAgents analysis results for a stock alert",
)
async def list_analysis_results(
    alert_id: int, limit: int = Query(10, ge=1, le=100), db: AsyncSession = Depends(get_db)
) -> list[AnalysisResult]:
    """List past TradingAgents analysis runs for a stock alert, most recent first.

    Args:
        alert_id: Primary key of the `StockAlert` row.
        limit: Max results to return (1-100, default 10).

    Returns:
        `AnalysisResult` rows for this alert's ticker, newest first.

    Raises:
        HTTPException: 404 if no alert exists with that ID.
    """
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
