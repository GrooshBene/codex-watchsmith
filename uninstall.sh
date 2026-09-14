#!/bin/zsh
set -e
C="${CODEX_HOME:-$HOME/.codex}"; B="$C/bin"; S="$C/watchsmith"; CFG="$C/config.toml"
R="${0:A:h}"
python3 -c 'import tomllib' 2>/dev/null || { print -u2 'Python 3.11+ is required'; exit 1; }
python3 "$R/bin/watchsmith_config.py" uninstall "$C"
rm -f "$B/activitysmith_notify.py" "$B/watchsmith_notify_dispatcher.py" "$B/codex-watch" "$B/activitysmith-keychain-setup" "$B/activitysmith-test"
print '✓ 실행 파일 제거 및 이전 notify 복원 시도 완료'
print 'ℹ AGENTS.md tagged block / Keychain key는 수동 검토를 위해 유지됩니다.'
