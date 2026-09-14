#!/usr/bin/env python3
import json, os, shutil, subprocess, sys
SERVICE='activitysmith-codex'
def get_key():
    if os.environ.get('ACTIVITYSMITH_API_KEY'):
        return os.environ['ACTIVITYSMITH_API_KEY']
    sec=shutil.which('security')
    if not sec: return None
    p=subprocess.run([sec,'find-generic-password','-a',os.environ.get('USER',''),'-s',SERVICE,'-w'],capture_output=True,text=True)
    return p.stdout.strip() if p.returncode==0 else None
def main():
    if len(sys.argv)!=2: return 0
    try: evt=json.loads(sys.argv[1])
    except Exception: return 0
    if evt.get('type')!='agent-turn-complete': return 0
    cli=shutil.which('activitysmith'); key=get_key()
    if not cli or not key: return 0
    env=os.environ.copy(); env['ACTIVITYSMITH_API_KEY']=key
    subprocess.Popen([cli,'push','--title','Codex 작업 완료','--message','요청한 에이전트 작업이 완료되었습니다.'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    return 0
if __name__=='__main__': raise SystemExit(main())
