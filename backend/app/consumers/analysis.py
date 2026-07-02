import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.event import Event
from app.models.stock_alert import StockAlert
from app.services import trading_agents

_log = logging.getLogger(__name__)


async def handle(event: Event, session: AsyncSession) -> None:
    if event.type != "STOCK_THRESHOLD":
        return

    payload = event.payload
    alert = await session.get(StockAlert, payload["alert_id"])
    if alert is None or not alert.run_analysis:
        return

    analysis = AnalysisResult(
        stock_alert_id=alert.id,
        event_id=event.id,
        ticker=payload["ticker"],
        triggered_price=payload["price"],
        status="pending",
    )
    session.add(analysis)
    # Must be a real commit, not just flush() — spawn() below hands the row off to a
    # background task that reads it on a *separate* connection. flush() only makes the
    # row visible within this transaction; a concurrent SELECT from another connection
    # would race the caller's later commit and could see nothing (silent no-op).
    await session.commit()
    _log.info(
        "AnalysisResult created (pending TradingAgents) for %s @ %.4f",
        payload["ticker"],
        payload["price"],
    )
    trading_agents.spawn(trading_agents.run_analysis(alert, analysis.id))
