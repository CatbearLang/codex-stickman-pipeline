"""Official Codex CLI bridge; authentication stays inside Codex.

Never reads or serializes auth files or tokens. No private HTTP endpoints.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from .errors import AuthError, ProviderError


def check_login():
    codex = shutil.which('codex')
    if not codex:
        return False, 'Install @openai/codex, then run codex login.'
    try:
        r = subprocess.run([codex, 'login', 'status'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False, 'Unable to check Codex. Run codex login status.'
    text = (r.stdout + r.stderr).lower()
    ok = r.returncode == 0 and 'chatgpt' in text
    return ok, 'ChatGPT login detected.' if ok else 'Run codex login and choose Sign in with ChatGPT.'


def execute(prompt, directory, *, model='', image=False, schema=None, timeout=900):
    ok, hint = check_login()
    if not ok:
        raise AuthError(hint)
    directory = Path(directory).resolve()
    result = directory / 'response.txt'
    codex = shutil.which('codex')
    if not codex:
        raise AuthError('Codex CLI is not on PATH. Run stickman check.')
    cmd = [codex, 'exec', '--skip-git-repo-check', '--ephemeral',
           '--ignore-user-config', '--ignore-rules', '--color', 'never',
           '--sandbox', 'workspace-write', '-C', str(directory),
           '-o', str(result)]
    if schema:
        cmd += ['--output-schema', str(Path(schema).resolve())]
    if model:
        cmd += ['--model', model]
    if image:
        cmd += ['--enable', 'image_generation']
    cmd += ['-']
    # Prevent inherited API-key mode. OAuth storage remains managed by Codex.
    env = {k: v for k, v in os.environ.items() if k not in ('OPENAI_API_KEY', 'CODEX_API_KEY')}
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           cwd=directory, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ProviderError('Codex timed out. Completed images remain cached; retry explicitly.') from None
    except OSError:
        raise ProviderError('Codex could not start. Run stickman check.') from None
    if r.returncode:
        # Do not echo potentially sensitive subprocess logs to user reports.
        tail = ((r.stderr or '') + '\n' + (r.stdout or '')).strip().splitlines()
        hint = tail[-1][:300] if tail else ''
        raise ProviderError(
            'Codex failed. Check codex login status, CLI version, account quota and image_generation access. '
            f'No provider fallback was used. (exit {r.returncode}' + (f': {hint})' if hint else ')'))
    return result.read_text(encoding='utf-8') if result.exists() else ''
