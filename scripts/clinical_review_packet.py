"""Bind human review records to exact draft code. Never authorize patient care."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

CLINICAL = {'clinical_ontology.py', 'radiology.py', 'fhir_ingest.py', 'motifs.py',
            'guideline_reports.py', 'fhir_sync.py', 'note_reader.py', 'ecg.py', 'outreach.py',
            'basis.py', 'loop_detector.py', 'temporal_hypergraph.py',
            'governance.py', 'second_reader.py'}


class ReviewError(ValueError):
    """Generic review failure; source content and reviewer details stay out of errors."""


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(['git', '--no-pager', *args], cwd=root,
                                       stderr=subprocess.DEVNULL, text=True)
    except (subprocess.CalledProcessError, OSError):
        raise ReviewError('Review source revision could not be checked') from None


def build(root: Path, base: str) -> Dict[str, Any]:
    root = root.resolve()
    if not re.fullmatch(r'[a-f0-9]{40}', base):
        raise ReviewError('An exact base commit is required')
    _git(root, 'cat-file', '-e', base + '^{commit}')
    changed = set(_git(root, 'diff', '--no-ext-diff', '--name-only', base, '--').splitlines())
    untracked = set(_git(root, 'ls-files', '--others', '--exclude-standard').splitlines())
    base_files = set(_git(root, 'ls-tree', '-r', '--name-only', base, '--',
                          'src', 'js', 'scripts').splitlines())
    rows = []
    for name in sorted(changed | untracked):
        path = Path(name)
        if path.parts[0] not in {'src', 'js', 'scripts'} or path.suffix not in {'.py', '.js', '.cjs'}:
            continue
        target = root / path
        if not target.resolve().is_relative_to(root):
            raise ReviewError('Review source must stay inside the checkout')
        # Staging changes Git bookkeeping, not the reviewed source or its scope.
        if name not in base_files:
            hunks = ['new file: review every line']
        else:
            diff = _git(root, 'diff', '--no-ext-diff', '--unified=0', base, '--', name)
            hunks = [line for line in diff.splitlines() if line.startswith('@@')]
        rows.append({'file': name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None,
                     'changed_hunks': hunks, 'requires_clinician': path.name in CLINICAL,
                     'reviewer': None, 'reviewer_role': None, 'reviewed_at': None,
                     'decision': 'pending', 'line_by_line_review_complete': False, 'notes': []})
    return {'format_version': 1, 'base_commit': base, 'files': rows,
            'software_tests_do_not_approve_clinical_use': True,
            'runtime_rule_signoffs_created': False}


def verify(packet: Dict[str, Any], root: Path, base: str) -> Dict[str, Any]:
    expected = build(root, base)
    if (packet.get('format_version') != 1 or packet.get('base_commit') != base
            or packet.get('runtime_rule_signoffs_created') is not False
            or packet.get('software_tests_do_not_approve_clinical_use') is not True
            or not isinstance(packet.get('files'), list) or not expected['files']
            or len(packet['files']) != len(expected['files'])):
        raise ReviewError('Review packet is incomplete or does not match this candidate')
    decisions = []
    for row, source in zip(packet['files'], expected['files']):
        if not isinstance(row, dict) or any(row.get(k) != source[k] for k in
                ['file', 'sha256', 'changed_hunks', 'requires_clinician']):
            raise ReviewError('Review is stale or its source scope changed')
        decision = row.get('decision')
        if decision not in {'approved', 'pending', 'changes_requested'}:
            raise ReviewError('Unknown review decision')
        if decision != 'pending':
            reviewer = row.get('reviewer')
            role = row.get('reviewer_role')
            if (not isinstance(reviewer, str) or len(reviewer.strip()) < 3
                    or reviewer.strip().casefold() in {'none', 'pending', 'unknown', 'chatgpt', 'codex', 'ai assistant'}
                    or role not in {'clinician', 'ml_researcher', 'software_engineer'}
                    or (source['requires_clinician'] and role != 'clinician')):
                raise ReviewError('An accountable human reviewer with the appropriate role is required')
            try:
                when = datetime.fromisoformat(row['reviewed_at'].replace('Z', '+00:00'))
                if when.tzinfo is None or when > datetime.now(timezone.utc):
                    raise ValueError()
            except (KeyError, AttributeError, ValueError, TypeError):
                raise ReviewError('A valid dated human review record is required') from None
            if decision == 'approved' and row.get('line_by_line_review_complete') is not True:
                raise ReviewError('Approval requires line-by-line review of the exact candidate')
        decisions.append(decision)
    status = ('CHANGES_REQUESTED' if 'changes_requested' in decisions else 'PENDING_HUMAN_REVIEW'
              if 'pending' in decisions else 'REVIEW_RECORDS_COMPLETE_NOT_CLINICAL_VALIDATION')
    return {'status': status, 'files': len(decisions), 'approved': decisions.count('approved'),
            'pending': decisions.count('pending'), 'changes_requested': decisions.count('changes_requested'),
            'clinical_use_authorized': False, 'runtime_rule_signoffs_created': False,
            'qualification_check': 'Reviewer qualifications and independence require external human verification'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--base', required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path)
    action.add_argument('--check', type=Path)
    args = parser.parse_args()
    try:
        if args.output:
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(build(args.root, args.base), stream, indent=2, ensure_ascii=False)
                stream.write('\n')
            print('Pending human review packet written. No clinical approval or rule sign-off created.')
        else:
            result = verify(json.loads(args.check.read_text()), args.root, args.base)
            print(json.dumps(result))
            if result['status'] != 'REVIEW_RECORDS_COMPLETE_NOT_CLINICAL_VALIDATION':
                raise SystemExit(2)
    except (ReviewError, OSError, ValueError, TypeError):
        parser.exit(1, 'Review packet could not be verified. No clinical approval created.\n')


if __name__ == '__main__':
    main()
