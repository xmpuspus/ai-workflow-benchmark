#!/usr/bin/env python3
"""Generate a LinkedIn-worthy showcase GIF demonstrating AWB v0.5.2."""
import sys
sys.path.insert(0, "/Users/xavier/.claude/skills/terminal-gif")
from terminal_gif import TerminalGIF, G, D, F, C, Y, R

OUT = "/Users/xavier/Desktop/ai-workflow-benchmark/demos/awb-showcase.gif"

gif = TerminalGIF(preset="full", title="AI Workflow Benchmark v0.5.2")

# --- Scene 1: Install + Version ---
gif.pause(500)

s1 = [
    [D("$"), F(" pip install awb")],
    [G("Successfully installed"), F(" awb-"), Y("0.5.2")],
    "",
    [D("$"), F(" awb --version")],
    [C("awb"), F(", version "), Y("0.5.2")],
    "",
    [D("$"), F(" awb tools")],
    [F("  claude-code-vanilla   "), G("Available")],
    [F("  claude-code-custom    "), G("Available")],
    [F("  cursor                "), Y("Stub")],
    [F("  aider                 "), Y("Stub")],
]
gif.add_frame(s1, ms=2500)

# --- Scene 2: Validate 80 tasks ---
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

# --- Scene 3: Run with live progress ---
s3 = [
    [D("$"), F(" awb run --runs 3 --parallel -j 3 --adaptive")],
    "",
    [C("--- Run 1/3 ---"), F("  (80 tasks, saving to results/runs/...)")],
    [F("  [1/240] BF-001 (easy) ..."), G(" PASS"), F("  100/100  67s  $0.42")],
    [F("  [2/240] BF-003 (hard) ..."), R(" FAIL"), F("   75/100 143s  $0.81")],
    [F("  [3/240] BF-004 (easy) ..."), G(" PASS"), F("  100/100  52s  $0.35")],
    [D("  ... 77 more tasks ...")],
    [F("  "), G("Run 1 complete:"), F(" 44/80 passed (55%)")],
    "",
    [Y("Adaptive: 44 decisive (skip), 36 near-miss (re-run)")],
    "",
    [C("--- Run 2/3 ---"), F("  (36 near-miss tasks)")],
    [F("  [81/240] BF-003 (hard) ..."), R(" FAIL"), F("   75/100  98s  $0.65")],
    [D("  ... 35 more near-miss tasks ...")],
]
gif.add_frame(s3, ms=3500)

# --- Scene 4: Workflow Lift Score ---
s4 = [
    "",
    [F("  "), G("Workflow Lift: +4.2 pts"), F("  (p=0.031, "), G("significant"), F(")")],
    [F("  Pass rate: vanilla 55% vs custom 59%")],
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

# --- Scene 5: Stability + Calibration ---
s5 = [
    [D("$"), F(" awb stability results/runs/*")],
    "",
    [F("  Task     Mean   Std Dev  Range  Status")],
    [D("  ─────────────────────────────────────────")],
    [F("  FA-003    30%    42.4     90    "), R("UNSTABLE")],
    [F("  RF-003    77%    25.2     60    "), R("UNSTABLE")],
    [F("  BF-014    56%    18.9     40    "), R("UNSTABLE")],
    [F("  BF-001    90%     5.1     25    "), G("stable")],
    [D("  ... 76 more tasks ...")],
    "",
    [D("$"), F(" awb calibrate-difficulty results/runs/* --apply")],
    [Y("59/80 tasks recalibrated"), F(" (empirical pass rates)")],
    "",
    [D("$"), F(" awb calibrate-timeouts results/runs/* --apply")],
    [Y("74/80 tasks tightened"), F(" (p95 x 2.5)")],
]
gif.add_frame(s5, ms=4000)

# --- Scene 6: Gap Analysis ---
s6 = [
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
gif.add_frame(s6, ms=3500)

# --- Scene 7: CTA ---
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
    [F("  │  "), G("awb run --parallel --adaptive"), F("       │")],
    [F("  │                                        │")],
    [F("  │  "), D("github.com/xmpuspus/"), F("                │")],
    [F("  │  "), D("  ai-workflow-benchmark"), F("              │")],
    [F("  │                                        │")],
    [F("  └────────────────────────────────────────┘")],
]
gif.add_frame(s7, ms=5000)

gif.save(OUT)
print(f"Created {OUT}")
