import sys

sys.path.insert(0, "/Users/xavier/.claude/skills/terminal-gif")
from terminal_gif import C, D, F, G, R, TerminalGIF, Y

DEMOS = "/Users/xavier/Desktop/ai-workflow-benchmark/demos"


# ---- cli-version.gif ----
gif = TerminalGIF(preset="compact", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb --version", [
    "",
    [F("awb, version 1.1.3")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-version.gif")
print("Created cli-version.gif")


# ---- cli-tools.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb tools", [
    "",
    [F("               Available Tool Adapters")],
    [D(" --------------------------------------------------------")],
    [D("  Name                  Display Name             Status")],
    [D(" --------------------------------------------------------")],
    [F("  aider                 Aider                    "), D("Stub")],
    [F("  claude-code-custom    Claude Code (Custom)     "), G("Available")],
    [F("  claude-code-vanilla   Claude Code (Vanilla)    "), G("Available")],
    [F("  codex-cli             Codex CLI                "), G("Available")],
    [F("  copilot               GitHub Copilot CLI       "), R("Not found")],
    [F("  cursor                Cursor                   "), D("Stub")],
    [F("  gemini-cli            Gemini CLI               "), R("Not found")],
    [F("  pi                   Pi (Full Config)          "), G("Available")],
    [F("  windsurf              Windsurf                 "), R("Not found")],
    [D(" --------------------------------------------------------")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-tools.gif")
print("Created cli-tools.gif")


# ---- cli-validate.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb validate", [
    "",
    [G("PASS"), F(" bug-fix/BF-001.yaml")],
    [G("PASS"), F(" bug-fix/BF-003.yaml")],
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
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-validate.gif")
print("Created cli-validate.gif")


# ---- cli-info.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb info BF-001", [
    "",
    [F("BF-001 - Fix response_model silently dropping extra fields in FastAPI")],
    "",
    [F("  Category:     "), C("bug-fix")],
    [F("  Difficulty:   "), Y("medium")],
    [F("  Time:         "), F("15 min (timeout: 519s)")],
    [F("  Languages:    "), F("python")],
    [F("  Capabilities: "), C("framework_knowledge"), F(", "), C("test_writing")],
    [F("  Tags:         "), D("fastapi, pydantic, response-model, validation")],
    [F("  Repo:         "), F("https://github.com/tiangolo/fastapi")],
    [F("  Commit:       "), D("628c34e0cae2")],
    [F("  Max iters:    "), Y("15")],
    "",
    [F("  Partial Credit (100 pts):")],
    [F("    ["), Y("25"), F("] Test file created with ConfigDict extra=forbid model")],
    [F("    ["), Y("25"), F("] Uses Pydantic v2 ConfigDict (not v1 class Config)")],
    [F("    ["), Y("25"), F("] Test validates that extra fields raise error")],
    [F("    ["), Y("25"), F("] Tests pass")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-info.gif")
print("Created cli-info.gif")


# ---- cli-run-dryrun.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb run --dry-run --category bug-fix", [
    "",
    [F("  Tasks (dry run) — "), Y("12"), F(" tasks in "), C("bug-fix")],
    "",
    [D("  ID      Title                                       Difficulty  Timeout")],
    [D("  ------  ------------------------------------------  ----------  -------")],
    [F("  BF-001  Fix response_model silently dropping extra  "), Y("medium"), F("      519s")],
    [F("  BF-003  Fix API client retry logic ignoring         "), Y("hard"), F("        649s")],
    [F("  BF-004  Fix None propagation through 3-layer        "), Y("easy"), F("        390s")],
    [F("  BF-005  Fix timezone-naive datetime comparison      "), Y("easy"), F("        524s")],
    [F("  BF-006  Fix async generator leaking DB connections  "), Y("easy"), F("        782s")],
    [F("  BF-008  Fix Pydantic silently truncating floats     "), Y("easy"), F("        430s")],
    [F("  BF-009  Fix circular import between models          "), Y("easy"), F("        843s")],
    [D("  ... 5 more ...")],
    "",
    [D("  12 tasks selected. Use --runs N to set repeat count (default: 3).")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-run-dryrun.gif")
print("Created cli-run-dryrun.gif")


# ---- cli-run.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb run claude-code-vanilla -t BF-001", [
    "",
    [F("Running "), Y("1"), F(" task(s) x "), Y("3"), F(" run(s) with "), C("claude-code-vanilla")],
    "",
    [D("  Cloning tiangolo/fastapi @ 628c34e...")],
    [D("  Running setup: venv + pip install...")],
    [G("  [1/3]"), F(" BF-001  "), Y("142.6s"), F("  "), G("PASS"), F("  100/100  $0.28  6 iters")],
    [G("  [2/3]"), F(" BF-001  "), Y("158.3s"), F("  "), G("PASS"), F("  100/100  $0.31  7 iters")],
    [G("  [3/3]"), F(" BF-001  "), Y("137.9s"), F("  "), G("PASS"), F("   75/100  $0.24  5 iters")],
    "",
    [D("  -------  -------  --------  ------  ------  ----------")],
    [D("  Task     Result   Score     Time    Cost    Iterations")],
    [D("  -------  -------  --------  ------  ------  ----------")],
    [F("  BF-001   "), G("PASS"), F("    100/100   142.6s  $0.28   6")],
    [F("  BF-001   "), G("PASS"), F("    100/100   158.3s  $0.31   7")],
    [F("  BF-001   "), G("PASS"), F("     75/100   137.9s  $0.24   5")],
    [D("  -------  -------  --------  ------  ------  ----------")],
    "",
    [D("  Results saved to results/runs/2026-03-26_run1/")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-run.gif")
print("Created cli-run.gif")


# ---- cli-compare.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb compare results/runs/custom_run results/runs/vanilla_run", [
    "",
    [F("  Comparison: "), C("claude-code-custom"), F(" vs "), C("claude-code-vanilla")],
    "",
    [D("  Task    Custom   Vanilla  Score-C  Score-V  Time-C  Time-V")],
    [D("  ------  -------  -------  -------  -------  ------  ------")],
    [F("  BF-001  "), G("PASS"), F("    "), G("PASS"), F("    100/100   75/100   143s    187s")],
    [F("  BF-003  "), G("PASS"), F("    "), R("FAIL"), F("     85/100   40/100   267s    412s")],
    [F("  FA-001  "), G("PASS"), F("    "), G("PASS"), F("    100/100   75/100   118s    165s")],
    [F("  FA-002  "), G("PASS"), F("    "), G("PASS"), F("    100/100   85/100   195s    234s")],
    [F("  RF-001  "), G("PASS"), F("    "), R("FAIL"), F("     90/100   55/100   312s    467s")],
    "",
    [D("  Summary:")],
    [F("    Custom:  "), G("5/5 pass"), F("  "),
     Y("95/100"), F("  "), Y("$0.52"), F("  "), Y("207s")],
    [F("    Vanilla: "), Y("3/5 pass"), F("  "),
     Y("66/100"), F("  "), Y("$0.74"), F("  "), Y("293s")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-compare.gif")
print("Created cli-compare.gif")


# ---- cli-gap.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb gap results/runs/vanilla_run", [
    "",
    [F("  Capability Radar — "), C("claude-code-vanilla")],
    "",
    [F("  code_comprehension    "), G("████████████████████"), F("  "), Y("91")],
    [F("  bug_diagnosis         "), G("███████████████░░░░░"), F("  "), Y("76")],
    [F("  multi_file_reasoning  "), Y("████████████░░░░░░░░"), F("  "), Y("61")],
    [F("  framework_knowledge   "), G("██████████████████░░"), F("  "), Y("84")],
    [F("  test_writing          "), Y("███████████░░░░░░░░░"), F("  "), Y("58")],
    [F("  refactoring_discipline"), Y("█████████░░░░░░░░░░░"), F("  "), Y("47")],
    [F("  security_awareness    "), R("███████░░░░░░░░░░░░░"), F("  "), Y("34")],
    [F("  completeness_tracking "), Y("████████████░░░░░░░░"), F("  "), Y("60")],
    "",
    [F("  Patterns detected:")],
    [F("    - Security review tasks fail 66% of the time (3/3 hard tasks)")],
    [F("    - Multi-file refactors score 20pts lower without workspace CLAUDE.md")],
    [F("    - Timeout budget exceeded on 4/5 legacy-code tasks")],
    "",
    [F("  Suggestions:")],
    [F("    1. Add security-focused system prompt for code-review category")],
    [F("    2. Provide repo-level CLAUDE.md with architecture summary")],
    [F("    3. Increase timeout budget for legacy-code tasks to 900s")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-gap.gif")
print("Created cli-gap.gif")


# ---- cli-export.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
cmd = "awb export results/runs/vanilla_run -o submission.json --submitter \"Acme AI\""
gif.command_scene(cmd, [
    "",
    [F("  Exporting results from "), C("results/runs/vanilla_run")],
    "",
    [D("  Tasks found:          "), Y("47")],
    [D("  Runs included:        "), Y("3")],
    [D("  Adapter:              "), C("claude-code-vanilla")],
    [D("  Submitter:            "), F("Acme AI")],
    "",
    [G("  Submission written to: "), F("submission.json")],
    "",
    [D("  Schema version:       "), F("1.0")],
    [D("  Overall pass rate:    "), Y("71.2%")],
    [D("  Mean composite score: "), Y("68.4")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-export.gif")
print("Created cli-export.gif")


# ---- cli-submit.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb submit submission.json", [
    "",
    [G("  Submission valid"), F(" (schema v1.0)")],
    "",
    [D("  Submitter:        "), F("Acme AI")],
    [D("  Adapter:          "), C("claude-code-vanilla")],
    [D("  Benchmark version:"), F("1.0.0")],
    [D("  Tasks:            "), Y("47")],
    [D("  Runs per task:    "), Y("3")],
    "",
    [F("  Results:")],
    [F("    Pass rate:       "), Y("71.2%"), F("  (33/47 tasks)")],
    [F("    Mean score:      "), Y("68.4"), F(" / 100")],
    [F("    Mean cost:       "), Y("$0.47"), F(" per task")],
    [F("    Mean time:       "), Y("218s"), F(" per task")],
    "",
    [F("  Top capabilities:  "), G("code_comprehension"), F(", "), G("framework_knowledge")],
    [F("  Weak capabilities: "), R("security_awareness"), F(", "), R("refactoring_discipline")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-submit.gif")
print("Created cli-submit.gif")


# ---- cli-compare-submissions.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb compare-submissions submission-a.json submission-b.json", [
    "",
    [F("  Cross-submission comparison")],
    "",
    [D("  Metric              Sub-A              Sub-B")],
    [D("  ----------------    ----------------   ----------------")],
    [F("  Submitter           "), F("Acme AI            "), F("Widgets Corp")],
    [F("  Adapter             "), C("claude-code-vanilla"), F("  "), C("claude-code-custom")],
    [F("  Tasks               "), Y("47"), F("                 "), Y("47")],
    [F("  Pass rate           "), Y("71.2%"), F("            "), Y("89.4%")],
    [F("  Mean score          "), Y("68.4"), F("             "), Y("84.1")],
    [F("  Mean cost           "), Y("$0.47"), F("            "), Y("$0.63")],
    [F("  Mean time           "), Y("218s"), F("             "), Y("197s")],
    "",
    [F("  Sub-B wins on: "), G("pass rate"), F(", "), G("score"), F(", "), G("speed")],
    [F("  Sub-A wins on: "), G("cost")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-compare-submissions.gif")
print("Created cli-compare-submissions.gif")


# ---- cli-leaderboard.gif ----
gif = TerminalGIF(preset="compact", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb leaderboard", [
    "",
    [G("Leaderboard generated: "), F("leaderboard/output/index.html")],
    [D("  4 tools, 12 submissions, 100 tasks")],
    [D("  Chart.js radar + CSV export + history tracking")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-leaderboard.gif")
print("Created cli-leaderboard.gif")


# ---- cli-migrate.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb migrate-results results/runs/", [
    "",
    [F("  Scanning for v0.5.x result files...")],
    "",
    [D("  Found 8 result files to migrate")],
    "",
    [G("  Migrated"), F(" results/runs/2026-03-20_132453_run1/result-BF-001.json")],
    [G("  Migrated"), F(" results/runs/2026-03-20_132453_run1/result-BF-003.json")],
    [G("  Migrated"), F(" results/runs/2026-03-20_132639_run1/result-BF-001.json")],
    [G("  Migrated"), F(" results/runs/2026-03-20_132639_run1/result-FA-001.json")],
    [D("  ... 4 more ...")],
    "",
    [G("  Migration complete. "), Y("8"), F(" files updated to v1.0 format.")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-migrate.gif")
print("Created cli-migrate.gif")


# ---- cli-stability.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb stability results/runs/run1 results/runs/run2 results/runs/run3", [
    "",
    [F("  Task Score Stability Report (3 runs)")],
    "",
    [D("  Task    Mean   Std Dev  Range   Status")],
    [D("  ------  -----  -------  ------  --------")],
    [F("  BF-001  "), Y("91.7"), F("   "), Y("12.3"), F("    75-100   "), G("stable")],
    [F("  BF-003  "), Y("60.0"), F("   "), Y("28.9"), F("    25-100   "), R("UNSTABLE")],
    [F("  FA-001  "), Y("100.0"), F("  "), Y("0.0"), F("     100-100  "), G("stable")],
    [F("  FA-002  "), Y("83.3"), F("   "), Y("14.4"), F("    75-100   "), G("stable")],
    [F("  RF-001  "), Y("50.0"), F("   "), Y("25.0"), F("    25-75    "), R("UNSTABLE")],
    [F("  DB-001  "), Y("75.0"), F("   "), Y("7.2"), F("     75-100   "), G("stable")],
    "",
    [D("  2 unstable tasks (score range > 50pts). Consider:")],
    [D("    - Increasing runs per task for these tasks")],
    [D("    - Reviewing task prompts for ambiguity")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-stability.gif")
print("Created cli-stability.gif")


# ---- cli-calibrate-difficulty.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
cmd = "awb calibrate-difficulty results/runs/run1 results/runs/run2 results/runs/run3"
gif.command_scene(cmd, [
    "",
    [F("  Difficulty Recalibration (3 runs, 47 tasks)")],
    "",
    [D("  Task    Current   Pass Rate  Recommended  Delta")],
    [D("  ------  --------  ---------  -----------  -----")],
    [F("  BF-001  "), Y("medium"), F("    100%       "), Y("easy"), F("       "), G("↓")],
    [F("  BF-003  "), Y("hard"), F("      42%       "), Y("hard"), F("       "), D("=")],
    [F("  FA-001  "), Y("easy"), F("      100%      "), Y("easy"), F("       "), D("=")],
    [F("  RF-001  "), Y("medium"), F("    17%       "), Y("hard"), F("       "), R("↑")],
    [F("  DB-005  "), Y("easy"), F("      25%       "), Y("medium"), F("     "), R("↑")],
    "",
    [D("  5 tasks recalibrated. Run with --apply to write changes.")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-calibrate-difficulty.gif")
print("Created cli-calibrate-difficulty.gif")


# ---- cli-calibrate-timeouts.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb calibrate-timeouts results/runs/run1 results/runs/run2 results/runs/run3", [
    "",
    [F("  Timeout Calibration (p95 wall-clock from 3 runs)")],
    "",
    [D("  Task    Current  p95 Time  Recommended  Headroom")],
    [D("  ------  -------  --------  -----------  --------")],
    [F("  BF-001  "), Y("519s"), F("    163s      "), Y("220s"), F("       "), G("-57%")],
    [F("  BF-003  "), Y("649s"), F("    610s      "), Y("750s"), F("       "), R("+15%")],
    [F("  FA-001  "), Y("390s"), F("    118s      "), Y("160s"), F("       "), G("-59%")],
    [F("  RF-001  "), Y("600s"), F("    487s      "), Y("600s"), F("       "), D("=")],
    [F("  DB-005  "), Y("430s"), F("    398s      "), Y("520s"), F("       "), R("+21%")],
    "",
    [D("  5 tasks need adjustment. Run with --apply to update YAML files.")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-calibrate-timeouts.gif")
print("Created cli-calibrate-timeouts.gif")


# ---- cli-workflow.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb workflow export", [
    "",
    [F("  Exporting workflow descriptor...")],
    "",
    [D("  Detected adapter:  "), C("claude-code-custom")],
    [D("  System prompt:     "), F("~/.claude/CLAUDE.md (2,847 tokens)")],
    [D("  Hooks:             "), Y("3"), F(" active (pre-tool, stop, post-tool)")],
    [D("  Skills:            "), Y("12"), F(" loaded")],
    [D("  MCP servers:       "), Y("2"), F(" (context7, telegram)")],
    "",
    [G("  Workflow descriptor written to: "), F("workflow.yaml")],
    "",
    [D("  Share this file with awb submit to allow fair comparisons")],
    [D("  between teams using different Claude Code configurations.")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-workflow.gif")
print("Created cli-workflow.gif")


# ---- cli-quickstart.gif ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb quickstart", [
    "",
    [F("  AWB Quickstart — verifying setup")],
    "",
    [G("  ✓"), F("  Tool adapter:  "), C("claude-code-vanilla"), F(" (Available)")],
    [G("  ✓"), F("  Task schema:   "), F("100 tasks valid")],
    [G("  ✓"), F("  Git + clone:   "), F("tiangolo/fastapi cloned OK")],
    [G("  ✓"), F("  Single run:    "), F("BF-001 "), G("PASS"), F(" (147s, $0.29, 6 iters)")],
    "",
    [G("  Setup looks good."), F(" Run a full benchmark with:")],
    [F("    awb run claude-code-vanilla --category bug-fix")],
    "",
])
gif.pause(3000)
gif.save(f"{DEMOS}/cli-quickstart.gif")
print("Created cli-quickstart.gif")


# ---- cli-warmup.gif (NEW in v1.1) ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb warmup --dry-run", [
    "",
    [F("                    Workspace Templates ("), Y("63"), F(" unique)")],
    [D(" ------------------------------------------------------------")],
    [D("  Key       Repo       Tasks  Setup")],
    [D(" ------------------------------------------------------------")],
    [F("  614592fc  fastapi    "), Y("23"), F("     pip install -e '.[all]'...")],
    [F("  7519e140  fastapi    "), Y("10"), F("     pip install -e '.[all]' pytest")],
    [F("  8233804a  httpx      "), Y(" 2"), F("     pip install pytest trio")],
    [F("  3db963d6  fastapi    "), Y(" 3"), F("     pip install -e '.[all]' ruff")],
    [F("  ab1a78c4  flask      "), Y(" 2"), F("     pip install flask pytest")],
    [D("  ... 58 more ...")],
    [D(" ------------------------------------------------------------")],
    "",
    [D("  63 templates to build, 100 tasks total")],
    "",
    [G("  Tip:"), F(" run "), C("awb warmup"), F(" once to cache setups, then subsequent")],
    [F("       benchmark runs copy templates in ~2s instead of ~45s.")],
    "",
])
gif.pause(3500)
gif.save(f"{DEMOS}/cli-warmup.gif")
print("Created cli-warmup.gif")


# ---- cli-fast-check.gif (NEW in v1.1) ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb run --fast-check claude-code-custom", [
    "",
    [C("  Fast-check mode:"), F(" 8 representative tasks, 1 run")],
    "",
    [D("  --- Run 1/1 ---  (8 tasks)")],
    [F("  [1/8] BF-001 (medium) ... "), G("PASS"), F("  100/100  65s  $0.46")],
    [F("  [2/8] CR-001 (hard)   ... "), G("PASS"), F("  100/100  152s $0.78")],
    [F("  [3/8] DB-001 (easy)   ... "), G("PASS"), F("  100/100  41s  $0.21")],
    [F("  [4/8] FA-001 (easy)   ... "), G("PASS"), F("   85/100  38s  $0.19")],
    [F("  [5/8] LC-001 (easy)   ... "), G("PASS"), F("  100/100  29s  $0.12")],
    [F("  [6/8] MF-001 (hard)   ... "), R("FAIL"), F("   60/100  287s $1.24")],
    [F("  [7/8] RF-001 (medium) ... "), G("PASS"), F("   80/100  94s  $0.51")],
    [F("  [8/8] WF-001 (easy)   ... "), G("PASS"), F("  100/100  52s  $0.24")],
    "",
    [D("  Run 1 complete: 7/8 passed (88%)")],
    "",
    [G("  Estimated full-suite score: 89 +/- 11")],
    [D("  (based on 8 representative tasks; run the full suite for CI)")],
    "",
])
gif.pause(3500)
gif.save(f"{DEMOS}/cli-fast-check.gif")
print("Created cli-fast-check.gif")


# ---- cli-progressive.gif (NEW in v1.1) ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb run --progressive claude-code-vanilla", [
    "",
    [D("  --- Run 1/3 ---  (100 tasks, sorted easy -> hard)")],
    [F("  [1/100] BF-004 "), Y("(easy)"), F("   ... "), G("PASS"), F("  100/100")],
    [F("  [2/100] DB-001 "), Y("(easy)"), F("   ... "), G("PASS"), F("  100/100")],
    [F("  [3/100] FA-001 "), Y("(easy)"), F("   ... "), G("PASS"), F("   85/100")],
    [F("  [4/100] LC-001 "), Y("(easy)"), F("   ... "), R("FAIL"), F("   25/100")],
    [F("  [5/100] WF-001 "), Y("(easy)"), F("   ... "), R("FAIL"), F("    0/100")],
    [D("  ... 43 more easy tasks ...")],
    [F("  [48/100] WF-023 "), Y("(easy)"), F("  ... "), R("FAIL"), F("   10/100")],
    "",
    [Y("  Progressive stop:"), F(" Easy pass rate "), R("32%"), F(" < 40% threshold.")],
    [F("                    Tool not ready for medium/hard.")],
    "",
    [G("  Saved:"), F(" 52 medium+hard tasks skipped (~$78, ~95 min)")],
    "",
])
gif.pause(3500)
gif.save(f"{DEMOS}/cli-progressive.gif")
print("Created cli-progressive.gif")


# ---- cli-use-uv.gif (NEW in v1.1) ----
gif = TerminalGIF(preset="full", title="zsh -- awb")
gif.pause(400)
gif.command_scene("awb run --use-uv -t BF-001 claude-code-custom", [
    "",
    [D("  Using uv pip install (10-30x faster than pip)")],
    "",
    [D("  --- Run 1/3 ---  (1 task)")],
    [F("  [1/1] BF-001 (medium) ... "), G("PASS"), F("  100/100  58s  $0.42")],
    [D("                              (setup: "), G("2s"), F(" template copy + "), G("3s"), F(" uv install)")],
    "",
    [G("  Run 1 complete:"), F(" 1/1 passed (100%)")],
    "",
    [D("  Tip: combine with --fast-check or --progressive to save tokens,")],
    [D("  or run "), C("awb warmup"), D(" once to cache setups across all runs.")],
    "",
])
gif.pause(3500)
gif.save(f"{DEMOS}/cli-use-uv.gif")
print("Created cli-use-uv.gif")


print("\nAll 22 CLI demo GIFs created successfully")
