# awb task from-pr demo - real recording against a real merged PR
# (xmpuspus/cloudwright#69, a production bug-fix PR with a regression test).
# Run with: vhs demos/from-pr.tape
# Produces: demos/from-pr.gif

Output demos/from-pr.gif

Set Shell zsh
Set FontFamily "Menlo"
Set FontSize 18
Set Width 1280
Set Height 760
Set Padding 20
Set TypingSpeed 28ms
Set Theme { "name": "AWB", "background": "#0c0c0f", "foreground": "#e6e6e6", "black": "#0c0c0f", "red": "#ef4444", "green": "#4ade80", "yellow": "#facc15", "blue": "#60a5fa", "magenta": "#c084fc", "cyan": "#22d3ee", "white": "#e6e6e6", "brightBlack": "#52525b", "brightRed": "#f87171", "brightGreen": "#86efac", "brightYellow": "#fde047", "brightBlue": "#93c5fd", "brightMagenta": "#d8b4fe", "brightCyan": "#67e8f9", "brightWhite": "#f4f4f5", "cursor": "#e6e6e6", "selection": "#52525b" }

Hide
Type "cd /tmp/awb-demo-rec && source /Users/xavier/Desktop/ai-workflow-benchmark/.venv/bin/activate && setopt interactive_comments && export FORCE_COLOR=1 && export PS1='%F{cyan}>%f ' && clear"
Enter
Sleep 800ms
Show

Sleep 700ms
Type "# turn a merged PR from one of my repos into a private benchmark task"
Enter
Sleep 900ms
Type "awb task from-pr https://github.com/xmpuspus/cloudwright/pull/69 --out tasks --category bug-fix"
Enter
Sleep 9s

Type "clear"
Enter
Sleep 400ms
Type "# pre-merge SHA pinned, the PR regression test overlaid onto the old tree"
Enter
Sleep 900ms
Type "head -13 tasks/BF-002.yaml"
Enter
Sleep 4200ms

Type "clear"
Enter
Sleep 400ms
Type "# graded rubric: overlaid tests 60, no regressions 30, source touched 10"
Enter
Sleep 900ms
Type "grep -A 10 '^verification:' tasks/BF-002.yaml"
Enter
Sleep 4200ms

Type "clear"
Enter
Sleep 400ms
Type "awb validate --task-dir tasks -v"
Enter
Sleep 2600ms

Type "# no model trained on what this repo does next - run it like any task set"
Enter
Sleep 900ms
Type "awb run claude-code-vanilla --tasks-dir tasks --dry-run"
Enter
Sleep 5s
