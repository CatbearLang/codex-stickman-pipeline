"""Reproducible allowlisted ZIP. Fail closed on unreviewed files or secret patterns."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

SKIP={'.git','.venv','__pycache__','.pytest_cache','build','dist',
      'MiProyecto','demo-local'}  # old workspaces and generated media are never shipped
PATTERNS={
 'private-key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'api-token':re.compile(rb'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{25,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{20,})'),
 'jwt':re.compile(rb'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}'),
 'private-home':re.compile(rb'(?:/Users|/home)/[a-zA-Z0-9._-]+/'),
 'windows-private-home':re.compile(rb'(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+[\\/]+'),
 'literal-secret':re.compile(rb'(?i)(?:api_key|access_token|refresh_token|client_secret)\s*[=:]\s*[\x22\x27][A-Za-z0-9_+/=-]{28,}[\x22\x27]'),
}
BANNED={'.env','auth.json','credentials.json','config.toml','.DS_Store'}

def paths(root):
 return sorted(p for p in root.rglob('*') if p.is_file() and not any(x in SKIP or x.endswith('.egg-info') for x in p.relative_to(root).parts) and p.suffix not in ('.pyc','.pyo'))

def scan(root, approved):
 errors=[]
 actual={p.relative_to(root).as_posix() for p in paths(root)}
 if actual != set(approved):
  errors.append({'category':'allowlist-mismatch','added':sorted(actual-set(approved)),'missing':sorted(set(approved)-actual)})
 for rel in approved:
  p=root/rel
  if not p.exists():continue
  if p.is_symlink() or p.resolve().is_relative_to(root.resolve()) is False:
   errors.append({'category':'unsafe-path','path':rel});continue
  if any(x in ('.stickman','.codex','.credentials') for x in Path(rel).parts):
   errors.append({'category':'runtime-state','path':rel})
  if p.name in BANNED or p.name == 'bank.lock' or p.suffix in ('.key','.pem','.p12'):
   errors.append({'category':'credential-file','path':rel})
  data=p.read_bytes()
  for label,pat in PATTERNS.items():
   if pat.search(data):errors.append({'category':label,'path':rel})
 return errors

def build(root,out):
 root=Path(root).resolve();out=Path(out)
 approved=(root/'tools/allowlist.txt').read_text(encoding='utf-8').splitlines()
 errors=scan(root,approved)
 if errors:raise SystemExit(json.dumps({'ok':False,'findings':errors},indent=2))
 out.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for rel in sorted(approved):
   info=zipfile.ZipInfo('stickman-video-kit/'+rel,date_time=(2026,9,20,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
   z.writestr(info,(root/rel).read_bytes())
 with zipfile.ZipFile(out) as z:
  assert z.testzip() is None
  assert len(z.infolist())==len(approved)
 report={'ok':True,'files':len(approved),'zip':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'findings':[],'method':'Exact reviewed allowlist; raw-byte secret patterns; private paths; credential filenames; symlinks; ZIP CRC.'}
 print(json.dumps(report,indent=2));return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--out',required=True);a=p.parse_args();build(a.root,a.out)
