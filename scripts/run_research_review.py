"""Start a personal SYNTHETIC-only gateway without exposing an API key in a browser."""
import getpass
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY') or getpass.getpass('OpenAI API key (hidden; research only): ')
    if not os.environ['OPENAI_API_KEY']:
        raise SystemExit('API key missing. Nothing started.')
    os.environ['CLINLOOP_RESEARCH_MODEL'] = os.environ.get('CLINLOOP_RESEARCH_MODEL') or input('OpenAI model ID with Structured Outputs support: ').strip()
    if not os.environ['CLINLOOP_RESEARCH_MODEL']:
        raise SystemExit('Model ID missing. Nothing started.')
    secret_dir = ROOT / 'data' / 'secrets' / 'research-review'
    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_dir.chmod(0o700)
    token = secrets.token_urlsafe(32)
    token_path = secret_dir / ('access-code-' + secrets.token_hex(6) + '.txt')
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(token + '\n')
    os.environ['CLINLOOP_RESEARCH_GATEWAY_TOKEN'] = token
    print('Gateway access code file:', token_path)
    print('Open the file privately and paste its code into the research workspace. Never paste the OpenAI API key.')
    print('Loopback gateway: http://127.0.0.1:18127. Synthetic research only; provider charges may apply.')
    from src.research_report_gateway import main as run
    try:
        run()
    finally:
        token_path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
