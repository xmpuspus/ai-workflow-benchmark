"""Build a Hugging Face dataset artifact from the bundled AWB task YAMLs.

Produces:
  huggingface/dataset/data/tasks.jsonl   one row per task (flattened, JSON-typed)
  huggingface/dataset/README.md          dataset card with HF YAML frontmatter
  huggingface/dataset/stats.json         distributions used to fill the card

Run from repo root:  python3 scripts/build_hf_dataset.py
"""

from __future__ import annotations

import collections
import glob
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TASK_GLOB = str(ROOT / "awb" / "tasks" / "**" / "*.yaml")
OUT = ROOT / "huggingface" / "dataset"
DATA = OUT / "data"


def task_files() -> list[Path]:
    files = []
    for f in glob.glob(TASK_GLOB, recursive=True):
        p = Path(f)
        if p.name.startswith("_") or "__pycache__" in p.parts:
            continue
        files.append(p)
    return sorted(files)


def to_row(d: dict) -> dict:
    """Flatten one task dict into a JSON-serializable row with stable columns."""
    repo = d.get("repo", {}) or {}
    ver = d.get("verification", {}) or {}
    prov = d.get("provenance", {}) or {}
    # constraints live both top-level and (sometimes) under verification across the set
    constraints = d.get("constraints", ver.get("constraints", [])) or []
    return {
        "id": d.get("id"),
        "category": d.get("category"),
        "title": d.get("title"),
        "difficulty": d.get("difficulty"),
        "estimated_minutes": d.get("estimated_minutes"),
        "languages": d.get("languages", []) or [],
        "issue": d.get("issue"),
        "repo_url": repo.get("url"),
        "repo_commit": repo.get("commit"),
        "repo_setup": repo.get("setup"),
        "tests": ver.get("tests", []) or [],
        "partial_credit": json.dumps(ver.get("partial_credit", []) or [], ensure_ascii=False),
        "constraints": json.dumps(constraints, ensure_ascii=False),
        "tags": d.get("tags", []) or [],
        "capabilities": d.get("capabilities", []) or [],
        "label": d.get("label"),
        "contamination_risk": d.get("contamination_risk"),
        "provenance_source_pr_url": prov.get("source_pr_url"),
        "provenance_created_at": prov.get("created_at"),
        "provenance_last_verified_at": prov.get("last_verified_at"),
        "has_workspace_claude_md": bool(d.get("workspace_claude_md")),
    }


def main() -> None:
    files = task_files()
    rows = [to_row(yaml.safe_load(p.read_text())) for p in files]

    DATA.mkdir(parents=True, exist_ok=True)
    jsonl = DATA / "tasks.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # distributions
    cats = collections.Counter(r["category"] for r in rows)
    diff = collections.Counter(r["difficulty"] for r in rows)
    langs = collections.Counter(l for r in rows for l in r["languages"])
    caps = collections.Counter(c for r in rows for c in r["capabilities"])
    repos = collections.Counter(r["repo_url"] for r in rows)
    labels = collections.Counter(r["label"] for r in rows)
    contam = collections.Counter(r["contamination_risk"] for r in rows)

    # task-set hash, mirrors awb's own scheme: sha256 over sorted yaml bytes
    h = hashlib.sha256()
    for p in files:
        h.update(p.read_bytes())
    task_set_hash = h.hexdigest()

    stats = {
        "n_tasks": len(rows),
        "task_set_hash": task_set_hash,
        "categories": dict(cats),
        "difficulty": dict(diff),
        "languages": dict(langs),
        "capabilities": dict(caps),
        "repos": dict(repos),
        "labels": dict(labels),
        "contamination_risk": dict(contam),
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")

    print(f"wrote {jsonl} ({len(rows)} rows)")
    print(f"task_set_hash={task_set_hash}")
    print(f"categories={dict(cats)}")
    print(f"difficulty={dict(diff)}")
    print(f"languages={dict(langs)}")
    print(f"repos={dict(repos)}")
    print(f"labels={dict(labels)} contamination_risk={dict(contam)}")


if __name__ == "__main__":
    main()
