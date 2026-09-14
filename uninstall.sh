#!/bin/zsh
set -e
C="${CODEX_HOME:-$HOME/.codex}"; B="$C/bin"; S="$C/watchsmith"; CFG="$C/config.toml"
python3 - "$CFG" "$S/previous_notify.json" <<'PY'
import json,re,sys
from pathlib import Path
cfg,prev=map(Path,sys.argv[1:])
if not cfg.exists(): raise SystemExit
old=json.loads(prev.read_text()) if prev.exists() else None; out=[]
for l in cfg.read_text().splitlines():
    if re.match(r'^\s*notify\s*=.*watchsmith_notify_dispatcher',l):
        if old: out.append('notify = '+json.dumps(old))
    else: out.append(l)
cfg.write_text('\n'.join(out).rstrip()+'\n')
PY
rm -f "$B/activitysmith_notify.py" "$B/watchsmith_notify_dispatcher.py" "$B/codex-watch" "$B/activitysmith-keychain-setup" "$B/activitysmith-test"
print '✓ 실행 파일 제거 및 이전 notify 복원 시도 완료'
print 'ℹ AGENTS.md tagged block / Keychain key는 수동 검토를 위해 유지됩니다.'
