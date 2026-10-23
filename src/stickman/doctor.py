"""Local setup checks with no media generation or secret values."""
import importlib.util
import shutil
import subprocess
import sys
from .codex_cli import check_login

def doctor(provider=None):
    checks={'Python 3.11+': sys.version_info >= (3,11)}
    for name in ('ffmpeg','ffprobe'):
        checks[name]=bool(shutil.which(name))
    checks['edge-tts']=importlib.util.find_spec('edge_tts') is not None
    if not provider or 'codex' in provider:
        ok,hint=check_login(); checks['Codex ChatGPT login']=ok; print(hint)
        codex = shutil.which('codex')
        if codex:
            r=subprocess.run([codex,'exec','--help'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
            checks['Codex CLI supports isolated execution']='--ignore-user-config' in r.stdout
            r=subprocess.run([codex,'features','list'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
            checks['Codex CLI includes image_generation']='image_generation' in r.stdout
    for label,ok in checks.items():print(('OK   ' if ok else 'FAIL ')+label)
    print('Readiness only: account image access, quota and network require a real generation. No credentials printed.')
    return 0 if all(checks.values()) else 2
