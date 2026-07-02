"""Headless TradingAgents runner.

Calls the TradingAgents library directly instead of its own CLI — that CLI
(``cli/main.py``) is an interactive ``questionary`` wizard with no way to
supply ticker, date, or analyst team non-interactively. This script must run
under the TradingAgents host venv's Python, with ``PYTHONPATH`` set to the
TradingAgents clone root, so ``import tradingagents`` resolves.

Prints exactly one line of JSON to stdout on success; all logging goes to
stderr so it can never corrupt that output. Exits non-zero on any failure.
"""

import argparse
import json
import logging
import sys

from _report_parsing import extract_executive_summary, extract_price_target

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("trade_date")
    parser.add_argument("--analysts", default="market,social,news,fundamentals")
    args = parser.parse_args()

    analysts = args.analysts.split(",")
    graph = TradingAgentsGraph(selected_analysts=analysts, config=DEFAULT_CONFIG)
    final_state, decision = graph.propagate(args.ticker, args.trade_date)

    final_trade_decision = final_state.get("final_trade_decision", "")
    price_target = extract_price_target(final_trade_decision)
    executive_summary = extract_executive_summary(final_trade_decision)

    report_path = graph.save_reports(final_state, args.ticker)

    print(
        json.dumps(
            {
                "decision": decision,
                "price_target": price_target,
                "executive_summary": executive_summary,
                "final_trade_decision": final_trade_decision,
                "market_report": final_state.get("market_report"),
                "sentiment_report": final_state.get("sentiment_report"),
                "news_report": final_state.get("news_report"),
                "fundamentals_report": final_state.get("fundamentals_report"),
                "report_path": str(report_path),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger(__name__).error("run_tradingagents failed", exc_info=True)
        sys.exit(1)
