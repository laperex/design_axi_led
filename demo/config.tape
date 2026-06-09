# config.tape — shared display settings + shell init
# Source this at the top of every scene tape (after setting Output).

Set Shell      "bash"
Set FontFamily "JetBrains Mono"
Set FontSize   14
Set Width      1440
Set Height     900
Set Padding    20
Set Framerate  30
Set TypingSpeed 40ms

Set Theme { "name": "simple", "black": "#1c1c1c", "red": "#cc6666", "green": "#99cc99", "yellow": "#f0c674", "blue": "#81a2be", "magenta": "#b294bb", "cyan": "#8abeb7", "white": "#c5c8c6", "brightBlack": "#666666", "brightRed": "#cc6666", "brightGreen": "#99cc99", "brightYellow": "#f0c674", "brightBlue": "#81a2be", "brightMagenta": "#b294bb", "brightCyan": "#8abeb7", "brightWhite": "#ffffff", "background": "#1c1c1c", "foreground": "#c5c8c6", "selection": "#373b41", "cursor": "#c5c8c6" }

# --- Shell init (hidden) -----------------------------------------------------
# zsh resets COLUMNS from pty on every prompt, so export here has no effect.
# Instead, every xviv call in scene tapes is prefixed with —
# shutil.get_terminal_size() checks os.environ['COLUMNS'] before the pty ioctl,
# so it wins even after zsh overwrites the shell variable.
# 114 = floor((1000px - 2*20px padding) / 8.4px per char, JetBrains Mono 14px)

Env TERM "xterm-256color"

Hide
Type "zsh"
Enter
Sleep 500ms
Type "source ~/.zshrc"
Enter
Sleep 500ms
Type "source .venv/bin/activate"
Enter
Sleep 500ms
Type "export PS1='~ '"
Enter
Sleep 1s
Ctrl+L
Sleep 300ms
Show
