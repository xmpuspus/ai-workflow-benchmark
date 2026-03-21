"""Adapter registry - discover and load tool adapters."""
from __future__ import annotations

from importlib.metadata import entry_points

from awb.adapters.base import ToolAdapter

# Fallback when the package is not installed via pip (e.g. direct script run)
_FALLBACK: dict[str, str] = {
    "claude-code-vanilla": "awb.adapters.claude_code:ClaudeCodeVanillaAdapter",
    "claude-code-custom": "awb.adapters.claude_code:ClaudeCodeCustomAdapter",
    "cursor": "awb.adapters.cursor:CursorAdapter",
    "aider": "awb.adapters.aider:AiderAdapter",
}

_cache: dict[str, type[ToolAdapter]] = {}


def reset_cache() -> None:
    """Clear the adapter cache (useful in tests)."""
    _cache.clear()


def _load_adapters() -> dict[str, type[ToolAdapter]]:
    if _cache:
        return _cache

    eps = entry_points(group="awb.adapters")
    if eps:
        for ep in eps:
            _cache[ep.name] = ep.load()
    else:
        # Not installed as a package; resolve fallback strings manually
        import importlib

        for name, ref in _FALLBACK.items():
            module_path, cls_name = ref.split(":")
            module = importlib.import_module(module_path)
            _cache[name] = getattr(module, cls_name)

    return _cache


def get_adapter(name: str) -> ToolAdapter:
    adapters = _load_adapters()
    if name not in adapters:
        available = ", ".join(adapters.keys())
        raise ValueError(f"Unknown adapter '{name}'. Available: {available}")
    return adapters[name]()


def list_adapters() -> list[tuple[str, str, bool]]:
    result = []
    for name, cls in _load_adapters().items():
        adapter = cls()
        try:
            available = adapter.check_available()
        except Exception:
            available = False
        result.append((name, adapter.display_name, available))
    return result
