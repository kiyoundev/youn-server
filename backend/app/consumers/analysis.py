import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.event import Event
from app.models.stock_alert import StockAlert

_log = logging.getLogger(__name__)


async def handle(event: Event, session: AsyncSession) -> None:
    if event.type != "STOCK_THRESHOLD":
        return

    payload = event.payload
    alert = await session.get(StockAlert, payload["alert_id"])
    if alert is None or not alert.run_analysis:
        return

    session.add(
        AnalysisResult(
            stock_alert_id=alert.id,
            event_id=event.id,
            ticker=payload["ticker"],
            triggered_price=payload["price"],
            status="pending",
        )
    )
    _log.info(
        "AnalysisResult created (pending TradingAgents) for %s @ %.4f",
        payload["ticker"],
        payload["price"],
    )
