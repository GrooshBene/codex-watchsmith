#!/bin/zsh
set -e
unsetopt BG_NICE
R="${0:A:h}"
python3 -c 'import tomllib' 2>/dev/null || { print -u2 'Python 3.11+ is required'; exit 1; }
python3 "$R/bin/watchsmith_install.py" uninstall "$@"
