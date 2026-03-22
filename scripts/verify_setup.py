#!/usr/bin/env python3
"""Verify that all task repos can be cloned and set up."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from awb.core.task_loader import load_all_tasks


def verify_task(task, workspace):
    """Clone repo and run setup. Returns (task_id, success, error)."""
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", task.repo.url, str(workspace)],
            capture_output=True, text=True, timeout=60, check=True,
        )
        subprocess.run(
            ["git", "checkout", task.repo.commit],
            capture_output=True, text=True, timeout=30, check=True,
            cwd=str(workspace),
        )
        return task.id, True, None
    except subprocess.CalledProcessError as e:
        return task.id, False, e.stderr[:200]
    except subprocess.TimeoutExpired:
        return task.id, False, "Timeout"


def main():
    tasks = load_all_tasks()
    print(f"Verifying {len(tasks)} tasks...\n")

    # Deduplicate by (url, commit)
    seen = set()
    unique_tasks = []
    for t in tasks:
        key = (t.repo.url, t.repo.commit)
        if key not in seen:
            seen.add(key)
            unique_tasks.append(t)

    print(f"Unique repo+commit combinations: {len(unique_tasks)}\n")

    passed = 0
    failed = 0
    for t in unique_tasks:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_id, success, error = verify_task(t, Path(tmpdir) / "repo")
            if success:
                print(f"  [PASS] {task_id} ({t.repo.url.split('/')[-1]})")
                passed += 1
            else:
                print(f"  [FAIL] {task_id}: {error}")
                failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(unique_tasks)} unique repos")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
