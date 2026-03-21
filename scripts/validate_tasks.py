#!/usr/bin/env python3
"""Validate all task YAML files against the schema."""
from awb.core.config import TASKS_DIR
from awb.core.task_loader import validate_task_yaml


def main():
    errors_found = False
    task_files = sorted(TASKS_DIR.rglob("*.yaml"))

    if not task_files:
        print("No task YAML files found")
        return

    for path in task_files:
        if path.name.startswith("_"):
            continue
        errors = validate_task_yaml(path)
        if errors:
            errors_found = True
            print(f"FAIL {path.relative_to(TASKS_DIR)}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"PASS {path.relative_to(TASKS_DIR)}")

    if errors_found:
        import sys
        sys.exit(1)
    print(f"\nAll {len(task_files)} tasks valid")


if __name__ == "__main__":
    main()
