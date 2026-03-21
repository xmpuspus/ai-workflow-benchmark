#!/usr/bin/env python3
"""Check which benchmark tools are available on this system."""
import sys

from awb.adapters.registry import list_adapters


def main():
    print("AI Workflow Benchmark - Tool Availability Check\n")
    adapters = list_adapters()

    for _, display_name, available in adapters:
        status = "AVAILABLE" if available else "NOT FOUND"
        print(f"  {display_name:30s} [{status}]")

    available_count = sum(1 for _, _, a in adapters if a)
    print(f"\n{available_count}/{len(adapters)} tools available")

    if available_count == 0:
        print("\nInstall at least one tool to run benchmarks.")
        sys.exit(1)


if __name__ == "__main__":
    main()
