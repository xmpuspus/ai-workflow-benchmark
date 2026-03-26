"""Track metrics during a tool run."""
from __future__ import annotations

import time

from awb.core.config import RunCost, RunMetrics

# Pricing per 1M tokens by model family
MODEL_PRICING: dict[str, dict[str, float]] = {
    "opus": {"input_per_m": 15.0, "output_per_m": 75.0},
    "sonnet": {"input_per_m": 3.0, "output_per_m": 15.0},
    "haiku": {"input_per_m": 0.25, "output_per_m": 1.25},
    "default": {"input_per_m": 15.0, "output_per_m": 75.0},
}

# Backward compat
INPUT_PRICE_PER_M = MODEL_PRICING["default"]["input_per_m"]
OUTPUT_PRICE_PER_M = MODEL_PRICING["default"]["output_per_m"]


class MetricCollector:
    def __init__(self) -> None:
        self._start: float = 0.0
        self._end: float = 0.0
        self._tool_calls: dict[str, int] = {}
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._iterations: int = 0
        self._final_cost: float | None = None

    def start(self) -> None:
        self._start = time.monotonic()

    def stop(self) -> None:
        self._end = time.monotonic()

    def record_tool_call(self, tool_name: str) -> None:
        self._tool_calls[tool_name] = self._tool_calls.get(tool_name, 0) + 1

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens

    def record_iteration(self) -> None:
        self._iterations += 1

    def parse_stream_event(self, event: dict) -> None:
        """Parse a Claude Code stream-json event and update counters."""
        if not isinstance(event, dict):
            return
        event_type = event.get("type", "")

        if event_type == "assistant":
            message = event.get("message", {})
            if isinstance(message, dict):
                usage = message.get("usage", {})
                if isinstance(usage, dict):
                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    if inp or out:
                        self.record_tokens(inp, out)
                # Count tool_use items in assistant message content
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            tool_name = item.get("name", "unknown")
                            self.record_tool_call(tool_name)
            self.record_iteration()

        elif event_type == "tool_use":
            tool_name = event.get("tool", event.get("name", "unknown"))
            self.record_tool_call(tool_name)

        elif event_type == "result":
            cost = event.get("total_cost_usd") or event.get("cost_usd")
            if cost is not None:
                self._final_cost = float(cost)
            # Extract token totals from result usage
            usage = event.get("usage", {})
            if isinstance(usage, dict):
                inp = usage.get("input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)
                out = usage.get("output_tokens", 0)
                total_input = inp + cache_read + cache_create
                if total_input or out:
                    # Replace accumulated values with authoritative totals
                    self._input_tokens = total_input
                    self._output_tokens = out
            # Extract iteration count from result
            num_turns = event.get("num_turns")
            if num_turns is not None:
                self._iterations = int(num_turns)

    @property
    def elapsed_seconds(self) -> float:
        if self._end > 0:
            return self._end - self._start
        if self._start > 0:
            return time.monotonic() - self._start
        return 0.0

    def to_metrics(self) -> RunMetrics:
        return RunMetrics(
            wall_clock_seconds=round(self.elapsed_seconds, 1),
            iteration_count=self._iterations,
            human_interventions=0,
            tool_calls=dict(self._tool_calls),
            files_modified=0,
            lines_changed=0,
        )

    def to_cost(self) -> RunCost:
        if self._final_cost is not None:
            estimated = self._final_cost
        else:
            estimated = (
                self._input_tokens / 1_000_000 * INPUT_PRICE_PER_M
                + self._output_tokens / 1_000_000 * OUTPUT_PRICE_PER_M
            )
        return RunCost(
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            estimated_cost_usd=round(estimated, 4),
        )
