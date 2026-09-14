#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
H=Path.home(); S=H/'.codex'/'watchsmith'; PREV=S/'previous_notify.json'; N=H/'.codex'/'bin'/'activitysmith_notify.py'
def main():
    if len(sys.argv)!=2: return 0
    payload=sys.argv[1]
    if PREV.exists():
        try:
            argv=json.loads(PREV.read_text())
            if isinstance(argv,list) and argv and 'watchsmith_notify_dispatcher.py' not in ' '.join(map(str,argv)):
                subprocess.Popen([*argv,payload],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except Exception: pass
    try: subprocess.Popen(['python3',str(N),payload],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except Exception: pass
    return 0
if __name__=='__main__': raise SystemExit(main())
