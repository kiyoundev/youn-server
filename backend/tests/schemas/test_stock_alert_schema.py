from datetime import datetime, timezone

from app.schemas.stock_alert import StockAlertResponse


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(
        id=1,
        ticker="AAPL",
        target_price=200.0,
        direction="above",
        alert_type="buy_signal",
        last_price=None,
        alerted_at=None,
        active=True,
        run_analysis=False,
        deep_think_llm=None,
        quick_think_llm=None,
        anthropic_effort=None,
        max_debate_rounds=None,
        max_risk_discuss_rounds=None,
        analysts=None,
        created_at=datetime.now(timezone.utc),
    )
    kwargs.update(overrides)
    return kwargs


def test_analysts_empty_string_from_db_maps_to_none():
    """POST /api/stockalerts with analysts=[] stores "" in the DB (CSV join of an
    empty list). Reading it back must not crash — "" means "not set", same as
    None, not a list containing one invalid empty-string entry."""
    response = StockAlertResponse(**_base_kwargs(analysts=""))
    assert response.analysts is None


def test_analysts_csv_from_db_splits_correctly():
    response = StockAlertResponse(**_base_kwargs(analysts="market,news"))
    assert response.analysts == ["market", "news"]


def test_analysts_none_stays_none():
    response = StockAlertResponse(**_base_kwargs(analysts=None))
    assert response.analysts is None


def test_analysts_list_passthrough():
    response = StockAlertResponse(**_base_kwargs(analysts=["market", "fundamentals"]))
    assert response.analysts == ["market", "fundamentals"]
