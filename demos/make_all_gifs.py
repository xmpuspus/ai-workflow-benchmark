import sys

sys.path.insert(0, "/Users/xavier/.claude/skills/terminal-gif")
from terminal_gif import C, D, F, G, R, TerminalGIF, Y

# ---- demo-tools.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)

tools_output = [
    "",
    [F("               Available Tool Adapters")],
    [D(" -------------------------------------------------------")],
    [D("  Name                  Display Name            Status")],
    [D(" -------------------------------------------------------")],
    [F("  claude-code-vanilla   Claude Code (Vanilla)   "), G("Available")],
    [F("  claude-code-custom    Claude Code (Custom)    "), G("Available")],
    [F("  gemini-cli            Gemini CLI              "), R("Not found")],
    [F("  codex-cli             Codex CLI               "), R("Not found")],
    [F("  pi                    Pi                      "), R("Not found")],
    [F("  cursor                Cursor                  "), R("Not found")],
    [F("  aider                 Aider                   "), R("Not found")],
    [F("  windsurf              Windsurf                "), R("Not found")],
    [F("  copilot               GitHub Copilot CLI      "), R("Not found")],
    [D(" -------------------------------------------------------")],
    "",
]
screen = gif.command_scene("awb tools", tools_output)
gif.pause(3000)
gif.save("/Users/xavier/Desktop/ai-workflow-benchmark/demos/demo-tools.gif")
print("Created demo-tools.gif")

# ---- demo-validate.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)

validate_output = [
    "",
    [G("PASS"), F(" bug-fix/BF-001.yaml")],
    [G("PASS"), F(" bug-fix/BF-002.yaml")],
    [G("PASS"), F(" code-review/CR-001.yaml")],
    [G("PASS"), F(" debugging/DB-001.yaml")],
    [G("PASS"), F(" feature-addition/FA-001.yaml")],
    [G("PASS"), F(" legacy-code/LC-001.yaml")],
    [G("PASS"), F(" multi-file/MF-001.yaml")],
    [G("PASS"), F(" refactoring/RF-001.yaml")],
    [G("PASS"), F(" workflow/WF-001.yaml")],
    [G("PASS"), F(" workflow/WF-002.yaml")],
    [D("  ... 90 more ...")],
    "",
    [G("All 100 tasks valid")],
    "",
]
screen = gif.command_scene("awb validate", validate_output)
gif.pause(3000)
gif.save("/Users/xavier/Desktop/ai-workflow-benchmark/demos/demo-validate.gif")
print("Created demo-validate.gif")

# ---- demo-run.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)

run_output = [
    "",
    [F("Running 1 task(s) x 3 run(s) with "), C("claude-code-vanilla")],
    "",
    [D("  Cloning tiangolo/fastapi @ 628c34e...")],
    [D("  Running setup: venv + pip install...")],
    [G("  [1/3]"), F(" BF-001 - "), Y("142.6s"), F(" - "), G("PASS"), F(" 100/100")],
    [G("  [2/3]"), F(" BF-001 - "), Y("158.3s"), F(" - "), G("PASS"), F(" 100/100")],
    [G("  [3/3]"), F(" BF-001 - "), Y("137.9s"), F(" - "), G("PASS"), F("  75/100")],
    "",
    [D(" -------------------------------------------------------")],
    [D("  Task     Success  Score    Time    Cost    Iterations")],
    [D(" -------------------------------------------------------")],
    [F("  BF-001   "), G("PASS"), F("    100/100  142.6s  $0.28   6")],
    [F("  BF-001   "), G("PASS"), F("    100/100  158.3s  $0.31   7")],
    [F("  BF-001   "), G("PASS"), F("     75/100  137.9s  $0.24   5")],
    [D(" -------------------------------------------------------")],
    "",
    [D("  Results saved to results/runs/2026-03-20_run*/")],
    "",
]
screen = gif.command_scene("awb run claude-code-vanilla -t BF-001", run_output)
gif.pause(3000)
gif.save("/Users/xavier/Desktop/ai-workflow-benchmark/demos/demo-run.gif")
print("Created demo-run.gif")

# ---- demo-compare.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)

compare_output = [
    "",
    [F("  Comparison: "), C("claude-code-custom"), F(" vs "), C("claude-code-vanilla")],
    "",
    [D("  Task     Custom   Vanilla  Custom   Vanilla  Time C  Time V")],
    [D("  -------  -------  -------  ------   -------  ------  ------")],
    [F("  BF-001   "), G("PASS"), F("    "), G("PASS"), F("    100/100  75/100   143s    187s")],
    [F("  BF-002   "), G("PASS"), F("    "), R("FAIL"), F("     85/100  40/100   267s    412s")],
    [F("  FA-001   "), G("PASS"), F("    "), G("PASS"), F("    100/100  75/100   118s    165s")],
    [F("  FA-002   "), G("PASS"), F("    "), G("PASS"), F("    100/100  85/100   195s    234s")],
    [F("  RF-001   "), G("PASS"), F("    "), R("FAIL"), F("     90/100  55/100   312s    467s")],
    "",
    [D("  Summary:")],
    [F("    Custom:  "), G("5/5 pass"), F("  avg "), Y("$0.52"), F("  avg "), Y("207s")],
    [F("    Vanilla: "), Y("3/5 pass"), F("  avg "), Y("$0.74"), F("  avg "), Y("293s")],
    "",
]
screen = gif.command_scene(
    "awb compare results/runs/custom_run results/runs/vanilla_run", compare_output
)
gif.pause(3000)
gif.save("/Users/xavier/Desktop/ai-workflow-benchmark/demos/demo-compare.gif")
print("Created demo-compare.gif")

# ---- demo-leaderboard.gif ----
gif = TerminalGIF(preset="compact", title="zsh -- awb")
gif.pause(400)

lb_output = [
    "",
    [G("Leaderboard generated: "), F("leaderboard/output/index.html")],
    [D("  9 tools, 15 results, 100 tasks")],
    [D("  Chart.js radar + CSV export + history tracking")],
    "",
]
screen = gif.command_scene("awb leaderboard", lb_output)
gif.pause(3000)
gif.save("/Users/xavier/Desktop/ai-workflow-benchmark/demos/demo-leaderboard.gif")
print("Created demo-leaderboard.gif")

print("\nAll GIFs created successfully")
