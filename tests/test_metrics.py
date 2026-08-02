"""Tests for MetricCollector and cost calculation."""

import time

import pytest

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


def test_cache_token_tracking():
    mc = MetricCollector()
    mc.parse_stream_event(
        {
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 100,
                    "cache_read_input_tokens": 2000,
                    "cache_creation_input_tokens": 300,
                },
                "content": [],
            },
        }
    )
    cost = mc.to_cost()
    assert cost.cache_read_tokens == 2000
    assert cost.cache_creation_tokens == 300


def test_result_event_overrides_cache_tokens():
    mc = MetricCollector()
    mc.parse_stream_event(
        {
            "type": "result",
            "usage": {
                "input_tokens": 5000,
                "output_tokens": 1000,
                "cache_read_input_tokens": 8000,
                "cache_creation_input_tokens": 500,
            },
        }
    )
    cost = mc.to_cost()
    assert cost.cache_read_tokens == 8000
    assert cost.cache_creation_tokens == 500
    assert cost.input_tokens == 5000 + 8000 + 500


def test_tokens_per_iteration():
    mc = MetricCollector()
    mc.record_tokens(10000, 5000)
    mc._iterations = 5
    assert mc.tokens_per_iteration == 3000.0


def test_tokens_per_iteration_zero_iters():
    mc = MetricCollector()
    mc.record_tokens(1000, 500)
    assert mc.tokens_per_iteration == 0.0


def test_cache_hit_ratio():
    mc = MetricCollector()
    mc._cache_read = 800
    mc._cache_create = 200
    mc._input_tokens = 0
    assert mc.cache_hit_ratio == 0.8


def test_cache_hit_ratio_zero():
    mc = MetricCollector()
    assert mc.cache_hit_ratio == 0.0


def test_per_iteration_tokens_tracked():
    mc = MetricCollector()
    mc.parse_stream_event(
        {
            "type": "assistant",
            "message": {
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [],
            },
        }
    )
    mc.parse_stream_event(
        {
            "type": "assistant",
            "message": {
                "usage": {"input_tokens": 200, "output_tokens": 80},
                "content": [],
            },
        }
    )
    per_iter = mc.per_iteration_tokens
    # 2 completed iterations + 1 pending (empty) current_iter
    assert len(per_iter) >= 2
    assert per_iter[0].input_tokens == 100
    assert per_iter[1].input_tokens == 200


def test_cost_includes_new_fields():
    mc = MetricCollector()
    mc._cache_read = 1000
    mc._cache_create = 500
    mc._thinking_tokens = 200
    cost = mc.to_cost()
    assert cost.cache_read_tokens == 1000
    assert cost.cache_creation_tokens == 500
    assert cost.thinking_tokens == 200


def test_parse_codex_turn_completed_usage_is_authoritative():
    mc = MetricCollector()
    mc.parse_stream_event(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 24_763,
                "cached_input_tokens": 24_448,
                "cache_write_input_tokens": 12,
                "output_tokens": 122,
                "reasoning_output_tokens": 9,
            },
        }
    )

    cost = mc.to_cost()
    assert cost.input_tokens == 24_763
    assert cost.cache_read_tokens == 24_448
    assert cost.cache_creation_tokens == 12
    assert cost.output_tokens == 122
    assert cost.thinking_tokens == 9
    assert mc.to_metrics().iteration_count == 1


def test_parse_codex_completed_items_counts_tool_calls_once():
    mc = MetricCollector()
    mc.parse_stream_event(
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "status": "completed"},
        }
    )
    mc.parse_stream_event(
        {
            "type": "item.completed",
            "item": {"type": "file_change", "status": "completed"},
        }
    )
    mc.parse_stream_event(
        {
            "type": "item.started",
            "item": {"type": "command_execution", "status": "in_progress"},
        }
    )

    mc.parse_stream_event(
        {
            "type": "item.completed",
            "item": {"type": "error", "message": "non-tool diagnostic"},
        }
    )

    assert mc.to_metrics().tool_calls == {"command_execution": 1, "file_change": 1}


def test_codex_credit_pricing_uses_cached_rate_and_retains_usd_equivalent():
    mc = MetricCollector(
        pricing={
            "billing_unit": "credits",
            "input_per_m": 125.0,
            "cached_input_per_m": 12.5,
            "output_per_m": 750.0,
            "usd_per_credit": 0.04,
        }
    )
    mc.parse_stream_event(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 332_051,
                "cached_input_tokens": 290_304,
                "output_tokens": 3_628,
                "reasoning_output_tokens": 1_703,
            },
        }
    )

    cost = mc.to_cost()

    assert cost.estimated_credits == pytest.approx(11.5682)
    assert cost.estimated_cost_usd == pytest.approx(0.4627)
