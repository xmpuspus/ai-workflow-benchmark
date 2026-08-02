# awb checkup demo: free static audit, then the full report from a saved run.
# Real recording, no synthesis. Requires a local probe run dir; re-record with:
#   vhs demos/checkup.tape
# (adjust the --from-run path to any saved checkup/run directory)

Output demos/checkup.gif

Set Shell zsh
Set FontFamily "Menlo"
Set FontSize 16
Set Width 1280
Set Height 900
Set Padding 18
Set TypingSpeed 25ms
Set Theme { "name": "AWB", "background": "#0c0c0f", "foreground": "#e6e6e6", "black": "#0c0c0f", "red": "#ef4444", "green": "#4ade80", "yellow": "#facc15", "blue": "#60a5fa", "magenta": "#c084fc", "cyan": "#22d3ee", "white": "#e6e6e6", "brightBlack": "#52525b", "brightRed": "#f87171", "brightGreen": "#86efac", "brightYellow": "#fde047", "brightBlue": "#93c5fd", "brightMagenta": "#d8b4fe", "brightCyan": "#67e8f9", "brightWhite": "#f4f4f5", "cursor": "#e6e6e6", "selection": "#52525b" }

Hide
Type "source .venv/bin/activate && export FORCE_COLOR=1 && export PS1='%F{cyan}>%f ' && clear"
Enter
Sleep 800ms
Show

Sleep 600ms
Type "awb checkup --tool codex-cli --static-only --config-dir demos/codex-demo-config --repo-dir ."
Enter
Sleep 4200ms

Type "clear"
Enter
Sleep 400ms
Type "awb checkup --tool codex-cli --from-run results/runs/2026-08-02_002909_run1 --config-dir demos/codex-demo-config --repo-dir ."
Enter
Sleep 8s
