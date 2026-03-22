#!/usr/bin/env python3
"""Generate a LinkedIn-worthy showcase GIF demonstrating AWB's full workflow."""
import sys
sys.path.insert(0, "/Users/xavier/.claude/skills/terminal-gif")
from terminal_gif import TerminalGIF, G, D, F, C, Y, R

OUT = "/Users/xavier/Desktop/ai-workflow-benchmark/demos/awb-showcase.gif"

gif = TerminalGIF(preset="full", title="zsh -- AI Workflow Benchmark")

# ─── Scene 1: Install ────────────────────────────────────────────────────────
gif.pause(500)

s1 = [
    [D("$"), F(" pip install awb")],
    [G("Successfully installed"), F(" awb-0.2.0")],
    "",
    [D("$"), F(" awb --version")],
    [C("awb"), F(", version "), Y("0.2.0")],
    "",
]
gif.add_frame(s1, ms=2500)

# ─── Scene 2: Validate ───────────────────────────────────────────────────────
s2 = [
    [D("$"), F(" awb validate")],
    "",
    [G("PASS"), F(" bug-fix/BF-001.yaml")],
    [G("PASS"), F(" bug-fix/BF-012.yaml")],
    [G("PASS"), F(" code-review/CR-008.yaml")],
    [G("PASS"), F(" debugging/DB-010.yaml")],
    [G("PASS"), F(" feature-addition/FA-009.yaml")],
    [G("PASS"), F(" legacy-code/LC-012.yaml")],
    [G("PASS"), F(" multi-file/MF-009.yaml")],
    [G("PASS"), F(" refactoring/RF-011.yaml")],
    [D("  ... 72 more ...")],
    "",
    [G("All 80 tasks valid")],
]
gif.add_frame(s2, ms=2500)

# ─── Scene 3: Run benchmark ──────────────────────────────────────────────────
s3 = [
    [D("$"), F(" awb run --runs 1")],
    "",
    [F("  Vanilla vs Custom — Side-by-Side")],
    [D("  ─────────────────────────────────────────")],
    [D("  Task     V-Pass  C-Pass  V-Score  C-Score")],
    [D("  ─────────────────────────────────────────")],
    [F("  BF-001   "), G("PASS"), F("    "), G("PASS"), F("   100/100 100/100")],
    [F("  BF-012   "), G("PASS"), F("    "), G("PASS"), F("   100/100 100/100")],
    [F("  CR-008   "), R("FAIL"), F("    "), R("FAIL"), F("    60/100 "), Y(" 75/100")],
    [F("  FA-009   "), R("FAIL"), F("    "), R("FAIL"), F("    70/100 "), Y(" 85/100")],
    [F("  LC-012   "), R("FAIL"), F("    "), R("FAIL"), F("    60/100 "), Y(" 80/100")],
    [D("  ... 75 more tasks ...")],
    "",
    [F("  Workflow: "), Y("88%"), F(" vs vanilla "), Y("85%"), F(" "), G("(+3%)")],
]
gif.add_frame(s3, ms=3500)

# ─── Scene 4: Gap Analysis ───────────────────────────────────────────────────
s4 = [
    [D("$"), F(" awb gap results/runs/latest/")],
    "",
    [C("claude-code-custom"), F(" — "), Y("88.3%")],
    "",
    [F("  Capability Profile:")],
    [F("  code comprehension  "), G("=================="), D("=="), F(" "), Y("92")],
    [F("  framework knowledge "), G("================="), D("==="), F(" "), Y("89")],
    [F("  security awareness  "), G("=================="), D("=="), F(" "), Y("91")],
    [F("  refactoring         "), G("================"), D("===="), F(" "), Y("86")],
    [F("  multi file reason.  "), G("==============="), D("====="), F(" "), Y("83")],
    [F("  bug diagnosis       "), G("=============="), D("======"), F(" "), Y("79")],
    [F("  test writing        "), G("==============="), D("====="), F(" "), Y("85")],
    [F("  cost discipline     "), G("==========="), D("========="), F(" "), Y("66")],
]
gif.add_frame(s4, ms=3500)

# ─── Scene 5: Gap suggestions ────────────────────────────────────────────────
s5 = [
    [F("  Top Improvement Actions:")],
    [F("  1. Add debugging methodology to config")],
    [F("  2. Enable subagent mode for >3 files")],
    [F("  3. Add test verification before stop")],
    "",
    [F("  Systematic Patterns:")],
    [F("  "), D("-"), F(" "), Y("94%"), F(" easy pass, "), Y("71%"), F(" hard pass")],
    [F("  "), D("-"), F(" Custom "), G("+12 pts"), F(" on multi-file")],
    [F("  "), D("-"), F(" Weakness: "), R("bug diagnosis"), F(" hard")],
    "",
    [D("$"), F(" awb export results/ -o my.json")],
    [G("Exported"), F(" 80 result(s) to "), C("my.json")],
    "",
    [D("$"), F(" awb submit my.json")],
    [G("Valid"), F(": 52/80 pass (65%)")],
]
gif.add_frame(s5, ms=3500)

# ─── Scene 6: CTA ────────────────────────────────────────────────────────────
s6 = [
    "",
    [F("  ┌────────────────────────────────────────┐")],
    [F("  │                                        │")],
    [F("  │  "), C("AI Workflow Benchmark (AWB)"), F("         │")],
    [F("  │                                        │")],
    [F("  │  "), Y("80"), F(" tasks across "), Y("7"), F(" capabilities    │")],
    [F("  │  Sigmoid scoring, gap analysis,     │")],
    [F("  │  capability profiles, statistics    │")],
    [F("  │                                        │")],
    [F("  │  "), G("pip install awb"), F("                     │")],
    [F("  │  "), G("awb run --runs 3"), F("                    │")],
    [F("  │                                        │")],
    [F("  │  "), D("github.com/xmpuspus/"), F("                │")],
    [F("  │  "), D("  ai-workflow-benchmark"), F("              │")],
    [F("  │                                        │")],
    [F("  └────────────────────────────────────────┘")],
]
gif.add_frame(s6, ms=5000)

gif.save(OUT)
print(f"Created {OUT}")
