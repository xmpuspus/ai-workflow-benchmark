from __future__ import annotations

from awb.core.config import RunEnvironment
from awb.core.evaluator import evaluator_identity, package_source_fingerprint
from awb.core.runner import BenchmarkRunner


def test_package_source_fingerprint_is_stable_and_changes_with_source(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "b.py").write_text("value = 2\n")
    (tmp_path / "nested" / "a.py").write_text("value = 1\n")

    first = package_source_fingerprint(tmp_path)
    assert first == package_source_fingerprint(tmp_path)

    (tmp_path / "nested" / "a.py").write_text("value = 3\n")
    assert package_source_fingerprint(tmp_path) != first


def test_evaluator_identity_includes_human_version_and_source_hash(tmp_path):
    (tmp_path / "evaluator.py").write_text("value = 1\n")

    identity = evaluator_identity("1.7.0", tmp_path)

    assert identity == f"1.7.0+source.{package_source_fingerprint(tmp_path)}"


def test_runner_caches_evaluator_identity_per_instance(monkeypatch):
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner._environment = RunEnvironment(awb_version="1.7.0")
    calls = []

    def identify(version):
        calls.append(version)
        return "1.7.0+source.test"

    monkeypatch.setattr("awb.core.runner.evaluator_identity", identify)

    assert runner._environment.awb_version == "1.7.0"
    assert runner._get_evaluator_version() == "1.7.0+source.test"
    assert runner._get_evaluator_version() == "1.7.0+source.test"
    assert calls == ["1.7.0"]
