"""Pure regex extraction from TradingAgents' rendered decision markdown.

Split out from run_tradingagents.py so this logic is unit-testable without
importing the tradingagents package itself (only available in the separate
host venv, not the backend's own dependencies).
"""

import re

_PRICE_TARGET_RE = re.compile(r"\*\*Price Target\*\*:\s*(-?[\d.]+)")
_EXECUTIVE_SUMMARY_RE = re.compile(
    r"\*\*Executive Summary\*\*:\s*(.+?)(?=\n\n\*\*|\Z)", re.DOTALL
)


def extract_price_target(markdown: str) -> float | None:
    match = _PRICE_TARGET_RE.search(markdown)
    return float(match.group(1)) if match else None


def extract_executive_summary(markdown: str) -> str | None:
    match = _EXECUTIVE_SUMMARY_RE.search(markdown)
    return match.group(1).strip() if match else None
