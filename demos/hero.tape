# AWB hero demo — real recording, no synthesis.
# Run with: vhs demos/hero.tape
# Produces: demos/hero.gif

Output demos/hero.gif

Set Shell zsh
Set FontFamily "Menlo"
Set FontSize 18
Set Width 1280
Set Height 760
Set Padding 20
Set TypingSpeed 28ms
Set Theme { "name": "AWB", "background": "#0c0c0f", "foreground": "#e6e6e6", "black": "#0c0c0f", "red": "#ef4444", "green": "#4ade80", "yellow": "#facc15", "blue": "#60a5fa", "magenta": "#c084fc", "cyan": "#22d3ee", "white": "#e6e6e6", "brightBlack": "#52525b", "brightRed": "#f87171", "brightGreen": "#86efac", "brightYellow": "#fde047", "brightBlue": "#93c5fd", "brightMagenta": "#d8b4fe", "brightCyan": "#67e8f9", "brightWhite": "#f4f4f5", "cursor": "#e6e6e6", "selection": "#52525b" }

Hide
Type "source .venv/bin/activate && export FORCE_COLOR=1 && export PS1='%F{cyan}>%f ' && clear"
Enter
Sleep 800ms
Show

Sleep 700ms
Type "awb checkup --tool codex-cli --static-only --config-dir demos/codex-demo-config --repo-dir ."
Enter
Sleep 4200ms

Type "clear"
Enter
Sleep 400ms
Type "awb validate"
Enter
Sleep 1600ms

Type "clear"
Enter
Sleep 400ms
Type "awb cost results/runs/2026-08-02_002909_run1/"
Enter
Sleep 3800ms

Type "clear"
Enter
Sleep 400ms
Type "awb workflow export codex-cli --config-dir demos/codex-demo-config -n codex-demo -o /tmp/awb-codex-demo.yaml"
Enter
Sleep 2600ms
