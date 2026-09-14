#!/bin/zsh
set -e
unsetopt BG_NICE
R="${0:A:h}"; C="${CODEX_HOME:-$HOME/.codex}"; B="$C/bin"; S="$C/watchsmith"; CFG="$C/config.toml"; A="$C/AGENTS.md"
command -v python3 >/dev/null || { print -u2 'Python 3.11+ is required'; exit 1; }
python3 -c 'import tomllib' 2>/dev/null || { print -u2 'Python 3.11+ is required'; exit 1; }
mkdir -p "$C"
python3 "$R/bin/watchsmith_config.py" install "$C"
mkdir -p "$B"
for f in activitysmith_notify.py watchsmith_notify_dispatcher.py codex-watch activitysmith-keychain-setup activitysmith-test; do cp "$R/bin/$f" "$B/$f"; chmod +x "$B/$f"; done
touch "$A"
if ! grep -q 'BEGIN codex-watchsmith activitysmith workflow' "$A"; then print '\n' >> "$A"; cat "$R/config/activitysmith-agents.md" >> "$A"; fi
print '✓ codex-watchsmith 설치 완료'
print '다음 단계:'
print '  npm i -g activitysmith-cli@latest'
print '  export PATH="$HOME/.codex/bin:$PATH"  # 필요 시 ~/.zshrc'
print '  activitysmith-keychain-setup'
print '  activitysmith-test'
print '  Codex 재시작'
