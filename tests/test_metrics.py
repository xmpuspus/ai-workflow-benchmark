"""Tests for MetricCollector and cost calculation."""

import time

from awb.core.metrics import MODEL_PRICING, MetricCollector


def test_model_pricing_has_expected_models():
    assert "opus" in MODEL_PRICING
    assert "sonnet" in MODEL_PRICING
    assert "haiku" in MODEL_PRICING
    assert "default" in MODEL_PRICING


def test_cost_calculation_default():
    mc = MetricCollector()
    mc.start()
    mc.record_tokens(1_000_000, 100_000)
    mc.stop()
    cost = mc.to_cost()
    expected = round(1.0 * 15.0 + 0.1 * 75.0, 4)
    assert cost.estimated_cost_usd == expected


def test_cost_zero_tokens():
    mc = MetricCollector()
    mc.start()
    mc.stop()
    cost = mc.to_cost()
    assert cost.estimated_cost_usd == 0.0


def test_elapsed_seconds():
    mc = MetricCollector()
    mc.start()
    time.sleep(0.05)
    mc.stop()
    assert mc.elapsed_seconds >= 0.04


def test_tool_call_tracking():
    mc = MetricCollector()
    mc.record_tool_call("Read")
    mc.record_tool_call("Read")
    mc.record_tool_call("Edit")
    metrics = mc.to_metrics()
    assert metrics.tool_calls == {"Read": 2, "Edit": 1}


def test_iteration_counting():
    mc = MetricCollector()
    for _ in range(3):
        mc.record_iteration()
    metrics = mc.to_metrics()
    assert metrics.iteration_count == 3


def test_parse_stream_event_assistant():
    mc = MetricCollector()
    mc.parse_stream_event(
        {
            "type": "assistant",
            "message": {
                "usage": {"input_tokens": 500, "output_tokens": 100},
                "content": [{"type": "tool_use", "name": "Read"}],
            },
        }
    )
    assert mc._input_tokens == 500
    assert mc._output_tokens == 100
    assert mc._iterations == 1


def test_parse_stream_event_result_overrides():
    mc = MetricCollector()
    mc.record_tokens(100, 50)
    mc.parse_stream_event(
        {
            "type": "result",
            "total_cost_usd": 1.23,
            "usage": {"input_tokens": 10000, "output_tokens": 5000},
            "num_turns": 7,
        }
    )
    cost = mc.to_cost()
    assert cost.estimated_cost_usd == 1.23
    assert cost.input_tokens == 10000


def test_parse_non_dict_ignored():
    mc = MetricCollector()
    mc.parse_stream_event("not a dict")
    mc.parse_stream_event(None)
    assert mc._iterations == 0
