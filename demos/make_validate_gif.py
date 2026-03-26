import sys
sys.path.insert(0, "/Users/xavier/.claude/skills/terminal-gif")
from terminal_gif import TerminalGIF, G, D, F

gif = TerminalGIF(preset="full", title="zsh -- awb")

gif.pause(400)

output = [
    "",
    [G("PASS"), F(" bug-fix/BF-001.yaml")],
    [G("PASS"), F(" bug-fix/BF-002.yaml")],
    [G("PASS"), F(" code-review/CR-001.yaml")],
    [G("PASS"), F(" debugging/DB-001.yaml")],
    [G("PASS"), F(" feature-addition/FA-001.yaml")],
    [G("PASS"), F(" feature-addition/FA-002.yaml")],
    [G("PASS"), F(" legacy-code/LC-001.yaml")],
    [G("PASS"), F(" multi-file/MF-001.yaml")],
    [G("PASS"), F(" refactoring/RF-001.yaml")],
    [G("PASS"), F(" refactoring/RF-002.yaml")],
    "",
    [G("All 10 tasks valid")],
    "",
]

screen = gif.command_scene("awb validate", output)
gif.pause(3000)

gif.save("/Users/xavier/Desktop/ai-workflow-benchmark/demos/demo-validate.gif")
print("Created demo-validate.gif")
