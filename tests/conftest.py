"""The unit suite must never start a billable Codex generation."""
import subprocess
import pytest
@pytest.fixture(autouse=True)
def prevent_remote_codex(monkeypatch):
 original=subprocess.run
 def guarded(argv,*a,**kw):
  if isinstance(argv,(list,tuple)) and str(argv[0]).endswith('codex'):
   raise AssertionError('Mock Codex in unit tests; live tests run separately.')
  return original(argv,*a,**kw)
 monkeypatch.setattr(subprocess,'run',guarded)
