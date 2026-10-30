"""FastAPI dependencies shared by more than one router. A getter used by a
single router stays in that router's module."""

from fastapi import Request

from app.services.ledger_cache import LedgerCache


def get_ledger_cache(request: Request) -> LedgerCache:
    return request.app.state.ledger_cache
