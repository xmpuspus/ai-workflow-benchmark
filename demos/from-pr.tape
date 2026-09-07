# awb task from-pr demo: generate a candidate from a real merged PR.
# Schema validation does not admit it; controls and independent review remain required.
# Prerequisite: current AWB venv at tmp/demo-env; GitHub CLI needs read access.

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
Type "source tmp/demo-env/bin/activate && mkdir -p tmp/from-pr-demo/tasks && find tmp/from-pr-demo/tasks -mindepth 1 -delete && setopt interactive_comments && export FORCE_COLOR=1 && export PS1='%F{cyan}>%f ' && clear"
Enter
Sleep 800ms
Show

Sleep 700ms
Type "# generate a benchmark candidate from a merged bug-fix PR"
Enter
Sleep 900ms
Type "awb task from-pr https://github.com/xmpuspus/cloudwright/pull/69 --out tmp/from-pr-demo/tasks --category bug-fix"
Enter
Sleep 9s

Type "clear"
Enter
Sleep 400ms
Type "# provenance is pinned to the pre-merge tree"
Enter
Sleep 900ms
Type "sed -n '1,16p' tmp/from-pr-demo/tasks/BF-002.yaml"
Enter
Sleep 4200ms

Type "clear"
Enter
Sleep 400ms
Type "awb validate --task-dir tmp/from-pr-demo/tasks -v"
Enter
Sleep 2600ms

Type "# schema-valid is still a candidate, not an admitted benchmark"
Enter
Sleep 900ms
Type "cat tmp/from-pr-demo/tasks/BF-002.review.json"
Enter
Sleep 5s
