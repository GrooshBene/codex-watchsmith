#!/bin/zsh
set -e
unsetopt BG_NICE
R="${0:A:h}"; C="${CODEX_HOME:-$HOME/.codex}"; B="$C/bin"; S="$C/watchsmith"; CFG="$C/config.toml"; A="$C/AGENTS.md"
mkdir -p "$B" "$S"
for f in activitysmith_notify.py watchsmith_notify_dispatcher.py codex-watch activitysmith-keychain-setup activitysmith-test; do cp "$R/bin/$f" "$B/$f"; chmod +x "$B/$f"; done
[[ -f "$CFG" ]] || touch "$CFG"
cp "$CFG" "$S/config.toml.backup.$(date +%Y%m%d-%H%M%S)"
python3 - "$CFG" "$S/previous_notify.json" "$B/watchsmith_notify_dispatcher.py" <<'PY'
import ast,json,re,sys
from pathlib import Path
cfg,prev,disp=map(Path,sys.argv[1:]); lines=cfg.read_text().splitlines(); out=[]; old=None; table=False; done=False
for line in lines:
    st=line.strip()
    if st.startswith('['): table=True
    if not table and re.match(r'^\s*notify\s*=',line):
        try:
            v=ast.literal_eval(line.split('=',1)[1].strip())
            if isinstance(v,list): old=v
        except: pass
        if not done: out.append(f'notify = ["python3", "{disp}"]'); done=True
        continue
    out.append(line)
if not done:
    i=next((i for i,l in enumerate(out) if l.strip().startswith('[')),len(out)); out.insert(i,f'notify = ["python3", "{disp}"]')
cfg.write_text('\n'.join(out).rstrip()+'\n')
if old and 'watchsmith_notify_dispatcher.py' not in ' '.join(map(str,old)): prev.write_text(json.dumps(old))
PY
touch "$A"
if ! grep -q 'BEGIN codex-watchsmith activitysmith workflow' "$A"; then print '\n' >> "$A"; cat "$R/config/activitysmith-agents.md" >> "$A"; fi
print '✓ codex-watchsmith 설치 완료'
print '다음 단계:'
print '  npm i -g activitysmith-cli@latest'
print '  export PATH="$HOME/.codex/bin:$PATH"  # 필요 시 ~/.zshrc'
print '  activitysmith-keychain-setup'
print '  activitysmith-test'
print '  Codex 재시작'
