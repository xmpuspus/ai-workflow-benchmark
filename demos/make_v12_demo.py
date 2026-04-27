"""Generate the v1.2.0 hero demo: trace grading + readiness score.

Uses a custom large-font preset so the GIF reads cleanly at 50% zoom for
social embeds and the README. The font and dimensions are deliberately
larger than the existing cli-*.gif demos.
"""

import sys
from pathlib import Path

from PIL import ImageFont

sys.path.insert(0, "/Users/xavier/.claude/skills/terminal-gif")
from terminal_gif import (  # noqa: E402
    C,
    D,
    F,
    G,
    PRESET_FULL,
    R,
    TerminalGIF,
    Y,
)

DEMOS = Path("/Users/xavier/Desktop/ai-workflow-benchmark/demos")
# Use Menlo so the ❯ prompt char renders cleanly at 32pt (Courier lacks it).
LARGE_FONT_PATH = "/System/Library/Fonts/Menlo.ttc"


def _large_preset() -> dict:
    """Override PRESET_FULL with substantially larger font + dimensions."""
    p = dict(PRESET_FULL)
    p.update(
        w=1280,
        h=720,
        font_size=32,
        padding=42,
        line_h=46,
        chrome_h=56,
        content_y_offset=20,
        btn_cx_start=22,
        btn_gap=36,
        btn_top=18,
        btn_bottom=38,
        btn_size=20,
        cursor_w=18,
        title_y=14,
    )
    return p


def make_large_gif(title: str = "zsh -- awb v1.2.0") -> TerminalGIF:
    """Construct a TerminalGIF and override its layout to the large preset."""
    gif = TerminalGIF(preset="full", title=title)
    p = _large_preset()
    gif.w = p["w"]
    gif.h = p["h"]
    gif.padding = p["padding"]
    gif.line_h = p["line_h"]
    gif.chrome_h = p["chrome_h"]
    gif.content_y_off = p["content_y_offset"]
    gif.btn_cx_start = p["btn_cx_start"]
    gif.btn_gap = p["btn_gap"]
    gif.btn_top = p["btn_top"]
    gif.btn_bottom = p["btn_bottom"]
    gif.btn_size = p["btn_size"]
    gif.cursor_w = p["cursor_w"]
    gif.title_y = p["title_y"]
    gif.font = ImageFont.truetype(LARGE_FONT_PATH, p["font_size"])
    return gif


def scene_one_run() -> None:
    """awb run: a fast-check completing with PASS rows."""
    gif = make_large_gif()
    gif.pause(500)
    gif.command_scene(
        "awb run --fast-check claude-code-custom",
        [
            "",
            [C("  Fast-check mode:"), F(" 8 representative tasks, 1 run")],
            "",
            [F("  [1/8] BF-001  "), G("PASS"), F("  100/100   65s   $0.46")],
            [F("  [2/8] CR-001  "), G("PASS"), F("  100/100  152s   $0.78")],
            [F("  [3/8] DB-001  "), G("PASS"), F("   85/100   41s   $0.21")],
            [F("  [4/8] WF-001  "), G("PASS"), F("  100/100   52s   $0.24")],
            "",
            [G("  trace.jsonl written: "), D("8 files, 312 spans (OTel-aligned)")],
            "",
        ],
    )
    gif.pause(2800)
    gif.save(str(DEMOS / "v12_run.gif"))


def scene_two_grade() -> None:
    """awb trace grade: 4 behavior scores per task."""
    gif = make_large_gif()
    gif.pause(500)
    gif.command_scene(
        "awb trace grade results/runs/2026-04-27_run1",
        [
            "",
            [F("  Trace Behavior Scores ("), Y("0-100"), F(")")],
            "",
            [D("  task              read_tests  ran_verif  in_scope  no_loop")],
            [D("  ----------------  ----------  ---------  --------  -------")],
            [F("  BF-001            "), G("100"), F("        "), G("100"), F("       "), G("100"), F("      "), G("100")],
            [F("  CR-001            "), Y(" 70"), F("        "), G("100"), F("       "), G("100"), F("      "), G("100")],
            [F("  DB-001            "), G("100"), F("        "), R("  0"), F("       "), G("100"), F("      "), Y(" 65")],
            [F("  WF-001            "), G("100"), F("        "), G("100"), F("       "), Y(" 50"), F("      "), G("100")],
            "",
            [D("  Behaviors: read tests before edit | verify after change |")],
            [D("             stay in scope | no failing-command loops")],
            "",
        ],
    )
    gif.pause(2800)
    gif.save(str(DEMOS / "v12_trace.gif"))


def scene_three_readiness() -> None:
    """awb leaderboard --readiness: composite Production Readiness Score."""
    gif = make_large_gif()
    gif.pause(500)
    gif.command_scene(
        "awb leaderboard --readiness",
        [
            "",
            [G("Leaderboard generated: "), F("results/leaderboard/index.html")],
            "",
            [F("  Production Readiness Score ("), Y("0-100"), F(")")],
            "",
            [D("  tool                              readiness")],
            [D("  --------------------------------  ---------")],
            [F("  claude-code-custom                     "), G("87.4")],
            [F("  claude-code-vanilla                    "), Y("71.8")],
            [F("  cursor                                 "), Y("64.2")],
            [F("  aider                                  "), R("48.9")],
            "",
            [D("  Composite of correctness, regression-safety, security,")],
            [D("  review burden, maintainability, cost, and speed.")],
            "",
        ],
    )
    gif.pause(3200)
    gif.save(str(DEMOS / "v12_readiness.gif"))


def scene_combined() -> None:
    """The single hero GIF embedded in the README — three beats in sequence.

    Each beat clears the screen so the GIF reads cleanly without overflow at
    1280x720. Pause durations let each scene breathe before the next command.
    """
    gif = make_large_gif()

    # Beat 1: a fast-check run completing with PASS rows + trace artifact.
    gif.pause(400)
    gif.command_scene(
        "awb run --fast-check claude-code-custom",
        [
            "",
            [C("  Fast-check:"), F(" 8 tasks, 1 run, ~15 min, ~$4")],
            [F("  [1/8] BF-001  "), G("PASS"), F("  100/100   65s   $0.46")],
            [F("  [2/8] CR-001  "), G("PASS"), F("  100/100  152s   $0.78")],
            [F("  [3/8] DB-001  "), G("PASS"), F("   85/100   41s   $0.21")],
            [D("  ... 5 more ...")],
            "",
            [G("  trace.jsonl written"), F(" (OTel-aligned, 312 spans)")],
            "",
        ],
    )
    gif.pause(2400)

    # Beat 2: trace grade — 4 behavior scores per task.
    gif.command_scene(
        "awb trace grade results/runs/2026-04-27_run1",
        [
            "",
            [F("  Trace Behavior Scores ("), Y("0-100"), F(")")],
            "",
            [D("  task    read_tests  ran_verif  in_scope  no_loop")],
            [F("  BF-001       "), G("100"), F("       "), G("100"), F("       "), G("100"), F("     "), G("100")],
            [F("  CR-001        "), Y("70"), F("       "), G("100"), F("       "), G("100"), F("     "), G("100")],
            [F("  DB-001       "), G("100"), F("         "), R("0"), F("       "), G("100"), F("      "), Y("65")],
            [F("  WF-001       "), G("100"), F("       "), G("100"), F("        "), Y("50"), F("     "), G("100")],
            "",
        ],
    )
    gif.pause(2600)

    # Beat 3: the Production Readiness Score composite.
    gif.command_scene(
        "awb leaderboard --readiness",
        [
            "",
            [F("  Production Readiness Score ("), Y("0-100"), F(")")],
            "",
            [D("  tool                  readiness")],
            [F("  claude-code-custom         "), G("87.4")],
            [F("  claude-code-vanilla        "), Y("71.8")],
            [F("  cursor                     "), Y("64.2")],
            [F("  aider                      "), R("48.9")],
            "",
        ],
    )
    gif.pause(3200)
    gif.save(str(DEMOS / "v12_trace_readiness.gif"))


if __name__ == "__main__":
    DEMOS.mkdir(parents=True, exist_ok=True)
    scene_combined()
    print("Created v12_trace_readiness.gif")
