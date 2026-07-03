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
import threading
from typing import Any

from _report_parsing import extract_executive_summary, extract_price_target

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import LLMResult  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402

_log = logging.getLogger(__name__)


class HeartbeatCallbackHandler(BaseCallbackHandler):
    """Tracks LLM/tool call counts and token usage, logging a HEARTBEAT line
    to stderr on every call start so the parent process (which can't see
    inside this subprocess) has a liveness signal to reset an idle timer on.

    Same counter shape as upstream's ``cli/stats_handler.py::StatsCallbackHandler``,
    plus the stderr logging that handler doesn't need (it reads its counters
    in-process at the end; we're crossing a process boundary).
    """

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def _heartbeat(self) -> None:
        _log.info(
            "HEARTBEAT llm_calls=%d tokens_in=%d tokens_out=%d tool_calls=%d",
            self.llm_calls,
            self.tokens_in,
            self.tokens_out,
            self.tool_calls,
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self.llm_calls += 1
        self._heartbeat()

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self.llm_calls += 1
        self._heartbeat()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        if usage_metadata:
            with self._lock:
                self.tokens_in += usage_metadata.get("input_tokens", 0)
                self.tokens_out += usage_metadata.get("output_tokens", 0)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self.tool_calls += 1
        self._heartbeat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("trade_date")
    parser.add_argument("--analysts", default="market,social,news,fundamentals")
    args = parser.parse_args()

    analysts = args.analysts.split(",")
    handler = HeartbeatCallbackHandler()
    graph = TradingAgentsGraph(
        selected_analysts=analysts, config=DEFAULT_CONFIG, callbacks=[handler]
    )
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
        _log.error("run_tradingagents failed", exc_info=True)
        sys.exit(1)
