#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
C=Path(__file__).resolve().parent.parent; PREV=C/'watchsmith'/'previous_notify.json'; N=C/'bin'/'activitysmith_notify.py'
def main():
    if len(sys.argv)!=2: return 0
    payload=sys.argv[1]
    if PREV.exists():
        try:
            argv=json.loads(PREV.read_text())
            if isinstance(argv,list) and argv and all(isinstance(arg, str) for arg in argv) and str(Path(__file__).resolve()) not in argv:
                subprocess.Popen([*argv,payload],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except Exception: pass
    try: subprocess.Popen([sys.executable,str(N),payload],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except Exception: pass
    return 0
if __name__=='__main__': raise SystemExit(main())
