# Synthetic Wealthsimple fixtures (issue #33)

**All data is fake** — account id `TEST-ACCT-0001`, invented trades and names. Never replace these with (or derive them from) a real export: a real export contains an account number and holdings.

**Header correction (2026-09-22):** there is no `transaction_date` column in any known export. The header is always `effective_date,effective_time,settlement_date,...`. Confirmed against a real 2026-09-20 export's header.

**No `settlement_date` fallback (decided 2026-09-22):** a row with blank `effective_date`/`effective_time` is rejected outright (`missing_effective_date`), not dated from `settlement_date` — the user doesn't expect this to occur in practice, and `settlement_date` runs ~1 day after the real date on trades, so silently substituting it would mis-date the row.

**No commission reconcile check (decided 2026-09-22):** dropped — the real export confirms `commission` is always `0` or blank (self-directed, commission-free trading). The column is still stored; nothing validates it.

**No footer handling (decided 2026-09-22):** dropped, along with `with_footer.csv`. The `"As of ... GMT-04:00"` footer was never actually seen in any real export — it came from one sentence in the original ticket text describing an older 2026-07-29 sample, unverified and now doubted by the user. The real 2026-09-20 export has no footer at all (checked directly: `tail` ends on the last data row, no trailing blank/text line). Same treatment as `transaction_date` and the `settlement_date` fallback: dropped rather than built against an unconfirmed spec claim.

## Files

| File | Purpose |
|---|---|
| `base.csv` | Full valid ledger, `effective_date` header |
| `missing_effective_date.csv` | Deposit + a trade with blank `effective_date`/`effective_time` → whole file must be rejected (`missing_effective_date`) |
| `with_sell.csv` | `base.csv` + one sell. **Sell strings (`SELL` / `SHORT`) are placeholders** — the real values are unconfirmed; update once a real sell is seen (see #33 verification items) |
| `unknown_type.csv` | Deposit + a `Fee`/`MANAGEMENT` row → whole file must be rejected |

There is deliberately no "US trade missing FX text" variant: a trade without `FX Rate:` text is CAD-native, never rejected (`.plan/33-wealthsimple-activity-import/challenges.md` #11).

## What `base.csv` exercises
- `quantity` overload: deposits, e-Transfer, dividend, tax and interest rows carry a *cash amount* in `quantity`; only `Trade` rows are shares.
- Two same-day `2026-01-31 00:00:00` $0.01 interest rows that differ only in description — both must survive import and re-import.
- USD trades carry `FX Rate: x` in the description; the CAD-listed `XEQT.TO` buy carries none.
- Zero-time automatic postings (dividend, tax, interest) vs real times on trades and deposits.

## Expected derived values (`base.csv`)

| Item | Expected |
|---|---|
| Rows | 9 |
| Cash balance (sum of `net_cash_amount`) | **869.14** |
| AAPL shares | 15 |
| AAPL native (USD) avg cost | (10 × 300.00/1.4500 + 5 × 306.60/1.4600) / 15 ≈ **207.93** (trade 1 = 206.90, trade 2 = 210.00) |
| AAPL CAD avg cost | (3000.00 + 1533.00) / 15 = **302.20** |
| XEQT.TO shares / native currency / avg cost | 20 / CAD / **30.00** |

With `with_sell.csv` (sell 5 AAPL, net +1575.00): AAPL shares 10, avg costs unchanged (207.93 USD / 302.20 CAD), cash **2444.14**.
