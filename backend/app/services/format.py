"""Price formatting shared by anything that renders a price as text on the
backend (issue #45's PRICE_DROP notification body — the only consumer for
now). Deliberately mirrors frontend/src/lib/format.ts's fmtPrice() rule for
rule — native currency, never FX-converted, same 3 branches — so a
Pushover notification and the watchlist UI never disagree about how a given
(amount, currency) pair reads."""


def format_price(amount: float, currency: str | None) -> str:
    if currency == "KRW":
        return f"₩{round(amount):,}"
    if currency == "USD":
        return f"${amount:.2f} USD"
    # CAD or None (unresolved) — matches the pre-#45 always-"$" behavior.
    return f"${amount:.2f}"
