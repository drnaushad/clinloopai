"""Start a personal SYNTHETIC-only gateway without exposing an API key in a browser."""
import getpass
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    provider = os.environ.get('CLINLOOP_RESEARCH_PROVIDER') or input('Research provider (openai / anthropic / gemini) [openai]: ').strip().lower() or 'openai'
    choices = {'openai': ('OPENAI_API_KEY', 'CLINLOOP_RESEARCH_MODEL'),
               'anthropic': ('ANTHROPIC_API_KEY', 'CLINLOOP_RESEARCH_ANTHROPIC_MODEL'),
               'gemini': ('GEMINI_API_KEY', 'CLINLOOP_RESEARCH_GEMINI_MODEL')}
    if provider not in choices:
        raise SystemExit('Unsupported provider. Nothing started.')
    key_var, model_var = choices[provider]
    os.environ[key_var] = os.environ.get(key_var) or getpass.getpass(provider + ' API key (hidden; research only): ')
    if not os.environ[key_var]:
        raise SystemExit('API key missing. Nothing started.')
    os.environ[model_var] = os.environ.get(model_var) or input(provider + ' model ID with JSON structured-output support: ').strip()
    if not os.environ[model_var]:
        raise SystemExit('Model ID missing. Nothing started.')
    secret_dir = ROOT / 'data' / 'secrets' / 'research-review'
    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_dir.chmod(0o700)
    token = 'clinloop_' + secrets.token_urlsafe(32)
    token_path = secret_dir / ('access-code-' + secrets.token_hex(6) + '.txt')
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(token + '\n')
    os.environ['CLINLOOP_RESEARCH_GATEWAY_TOKEN'] = token
    print('Gateway access code file:', token_path)
    print('Open the file privately and paste its code into the research workspace. Never paste a provider API key.')
    print('Loopback gateway: http://127.0.0.1:18127. Synthetic research only; provider charges may apply.')
    from src.research_report_gateway import main as run
    try:
        run()
    finally:
        token_path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
