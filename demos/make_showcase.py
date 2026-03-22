#!/usr/bin/env python3
"""Generate a LinkedIn-worthy showcase GIF demonstrating AWB v0.3.0."""
import sys
sys.path.insert(0, "/Users/xavier/.claude/skills/terminal-gif")
from terminal_gif import TerminalGIF, G, D, F, C, Y, R

OUT = "/Users/xavier/Desktop/ai-workflow-benchmark/demos/awb-showcase.gif"

gif = TerminalGIF(preset="full", title="AI Workflow Benchmark v0.3.0")

# ─── Scene 1: Install + Version ──────────────────────────────────────────────
gif.pause(500)

s1 = [
    [D("$"), F(" pip install awb")],
    [G("Successfully installed"), F(" awb-"), Y("0.3.0")],
    "",
    [D("$"), F(" awb --version")],
    [C("awb"), F(", version "), Y("0.3.0")],
    "",
    [D("$"), F(" awb tools")],
    [F("  claude-code-vanilla   "), G("Available")],
    [F("  claude-code-custom    "), G("Available")],
    [F("  cursor                "), Y("Stub")],
    [F("  aider                 "), Y("Stub")],
]
gif.add_frame(s1, ms=2500)

# ─── Scene 2: Validate 80 tasks ─────────────────────────────────────────────
s2 = [
    [D("$"), F(" awb validate")],
    "",
    [G("PASS"), F(" bug-fix/BF-012      "), D("test-first diagnosis")],
    [G("PASS"), F(" code-review/CR-008  "), D("review-only, no edits")],
    [G("PASS"), F(" debugging/DB-010    "), D("performance profiling")],
    [G("PASS"), F(" feature-addition/FA-009 "), D("ambiguous reqs")],
    [G("PASS"), F(" legacy-code/LC-012  "), D("20-file navigation")],
    [G("PASS"), F(" multi-file/MF-009   "), D("merge conflict")],
    [G("PASS"), F(" refactoring/RF-011  "), D("O(n^2) optimization")],
    [G("PASS"), F(" refactoring/RF-012  "), D("fix broken CI/CD")],
    [D("  ... 72 more ...")],
    "",
    [G("All 80 tasks valid"), F("  "), D("7 categories, 8 capabilities")],
]
gif.add_frame(s2, ms=3000)

# ─── Scene 3: Run + Workflow Lift Score ──────────────────────────────────────
s3 = [
    [D("$"), F(" awb run --runs 1")],
    "",
    [F("Running "), C("claude-code-vanilla"), F(" on "), Y("80"), F(" tasks")],
    [F("Running "), C("claude-code-custom"), F("  on "), Y("80"), F(" tasks")],
    "",
    [F("  Vanilla vs Custom — Side-by-Side")],
    [D("  ─────────────────────────────────────────")],
    [F("  BF-012   "), G("PASS"), F("  "), G("PASS"), F("   100/100  100/100")],
    [F("  BF-014   "), R("FAIL"), F("  "), R("FAIL"), F("    35/100  "), Y(" 75/100")],
    [F("  CR-008   "), R("FAIL"), F("  "), R("FAIL"), F("    60/100  "), Y(" 75/100")],
    [F("  DB-010   "), G("PASS"), F("  "), G("PASS"), F("   100/100  100/100")],
    [F("  LC-012   "), R("FAIL"), F("  "), R("FAIL"), F("    65/100  "), Y(" 80/100")],
    [D("  ... 75 more tasks ...")],
]
gif.add_frame(s3, ms=3000)

# ─── Scene 4: Workflow Lift Score ────────────────────────────────────────────
s4 = [
    "",
    [F("  "), G("Workflow Lift: +4.2 pts"), F("  (p=0.031, "), G("significant"), F(")")],
    [F("  Pass rate: vanilla 62% vs custom 68%")],
    [F("  Wins: custom 8 / vanilla 3 / ties 69")],
    "",
    [F("  "), C("Where your workflow helps:")],
    [F("    bug diagnosis         "), G("+12.3 pts"), F("  (26 tasks)")],
    [F("    multi file reasoning  "), G(" +8.1 pts"), F("  (23 tasks)")],
    [F("    security awareness    "), G(" +5.4 pts"), F("  (10 tasks)")],
    "",
    [F("  "), C("Where it hurts:")],
    [F("    cost discipline       "), R(" -4.2 pts"), F("  (80 tasks)")],
    "",
    [F("  "), C("Biggest task-level differences:")],
    [F("    BF-014  "), G("+40"), F("  (V=35  C=75)")],
]
gif.add_frame(s4, ms=4000)

# ─── Scene 5: Gap Analysis ──────────────────────────────────────────────────
s5 = [
    [D("$"), F(" awb gap results/runs/latest/")],
    "",
    [C("claude-code-custom"), F(" — "), Y("88.3%")],
    "",
    [F("  Capability Profile:")],
    [F("  code comprehension  "), G("=================="), D("=="), F(" "), Y("92")],
    [F("  framework knowledge "), G("================="), D("==="), F(" "), Y("89")],
    [F("  security awareness  "), G("=================="), D("=="), F(" "), Y("91")],
    [F("  bug diagnosis       "), G("==============="), D("====="), F(" "), Y("83")],
    [F("  multi file reason.  "), G("==============="), D("====="), F(" "), Y("83")],
    [F("  refactoring         "), G("================"), D("===="), F(" "), Y("86")],
    [F("  test writing        "), G("==============="), D("====="), F(" "), Y("85")],
    [F("  cost discipline     "), G("==========="), D("========="), F(" "), Y("66")],
]
gif.add_frame(s5, ms=3500)

# ─── Scene 6: Export + Share ─────────────────────────────────────────────────
s6 = [
    [D("$"), F(" awb export results/ -o my.json")],
    [G("Exported"), F(" 80 result(s) to "), C("my.json")],
    "",
    [D("$"), F(" awb submit my.json")],
    [G("Valid"), F(": claude-code-custom v2.1")],
    [F("  Tasks: "), Y("80"), F("  Pass rate: "), Y("68%")],
    "",
    [D("$"), F(" awb compare-submissions a.json b.json")],
    [F("  Significant: "), G("Yes"), F(" (p=0.03)")],
    [F("  Effect size: "), Y("0.42"), F(" ("), C("small-medium"), F(")")],
    "",
    [D("$"), F(" awb info BF-012")],
    [F("  "), C("BF-012"), F(" — test-first diagnosis")],
    [F("  Difficulty: medium | Capabilities: "), Y("2")],
    [F("  Partial Credit: "), Y("100 pts"), F(" across 5 criteria")],
]
gif.add_frame(s6, ms=3500)

# ─── Scene 7: CTA ───────────────────────────────────────────────────────────
s7 = [
    "",
    [F("  ┌────────────────────────────────────────┐")],
    [F("  │                                        │")],
    [F("  │  "), C("AI Workflow Benchmark"), F("               │")],
    [F("  │  "), D("Measure workflow, not just model"), F("    │")],
    [F("  │                                        │")],
    [F("  │  "), Y("80"), F(" tasks  "), D("|"), F("  "), Y("8"), F(" capabilities      │")],
    [F("  │  "), Y("7"), F(" categories "), D("|"), F(" Workflow Lift Score │")],
    [F("  │                                        │")],
    [F("  │  "), G("pip install awb"), F("                     │")],
    [F("  │  "), G("awb run --runs 3"), F("                    │")],
    [F("  │                                        │")],
    [F("  │  "), D("github.com/xmpuspus/"), F("                │")],
    [F("  │  "), D("  ai-workflow-benchmark"), F("              │")],
    [F("  │                                        │")],
    [F("  └────────────────────────────────────────┘")],
]
gif.add_frame(s7, ms=5000)

gif.save(OUT)
print(f"Created {OUT}")
