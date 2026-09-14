#!/bin/zsh
set -e
unsetopt BG_NICE
python3 -c 'import tomllib' 2>/dev/null || { print -u2 'Install Python 3.11+ first, then run setup again.'; exit 1; }
exec python3 -B "${0:A:h}/bin/watchsmith_setup.py" setup "$@"
