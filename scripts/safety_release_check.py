"""Track the Nov 6 safety repair candidate against exact software bytes.

This is an engineering provenance check, never clinical authorization. External
evidence cannot be replaced with a passing test count or an AI attestation.
"""
import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def source_digest(root: Path) -> str:
    tracked = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
    names = sorted({name for name in tracked if name and (
        Path(name).parts[0] in {'src', 'js', 'css', 'scripts', 'tests', '.github', 'demo'} or
        (Path(name).parts[0] == 'data' and name != 'data/safety_release_status.json') or
        name.endswith('.html') or name.startswith('requirements') or
        name in {'version.json', 'Dockerfile'})})
    rows = [(name, hashlib.sha256((root / name).read_bytes()).hexdigest())
            for name in names if (root / name).is_file()]
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def finding(number, state, en, ko, detail_en, detail_ko):
    return {'id': f'F{number:02d}', 'state': state, 'title': {'en': en, 'ko': ko},
            'detail': {'en': detail_en, 'ko': detail_ko}}


FINDINGS = [
    finding(1, 'repair_draft', 'Tissue follow-up scope', '조직 후속 조치 범위',
            'Wrong, missing or contradictory breast laterality cannot prove closure; supplied lesion/specimen references must match. Same-side evidence alone does not establish unique-lesion completion.',
            '유방 측성이 다르거나 누락·상충하면 종결 근거로 사용하지 않습니다. 제공된 병변·검체 참조가 일치해야 합니다. 같은 쪽의 근거만으로 특정 병변의 완료를 입증하지는 않습니다.'),
    finding(2, 'repair_draft', 'Word source integrity', 'Word 원문 무결성',
            'Reject superscript, subscript, strike-through and directional/positioned Word text instead of flattening medically meaningful formatting.',
            '의학적 의미가 있는 서식을 평탄화하지 않고 위·아래 첨자, 취소선, 방향·위치 지정 Word 텍스트를 거부합니다.'),
    finding(3, 'external_evidence_required', 'Clinical validation', '임상 검증',
            'Independent clinician source review, adjudicated all-eligible cohorts and prospective silent evaluation remain required. Synthetic results are not clinical accuracy.',
            '독립 의료진의 코드 검토, 적격 사례 전체에 대한 판정 코호트와 전향적 무음 평가가 필요합니다. 합성 결과는 임상 정확도가 아닙니다.'),
    finding(4, 'repair_draft', 'Model evidence integrity', '모델 근거 무결성',
            'Reject duplicate JSON keys and conflicting repeated-quote assertion contexts; keep source quotations unchanged. Heuristics do not prove semantic correctness.',
            'JSON 중복 키와 반복 인용의 상충 문맥을 거부하며 원문 인용은 보존합니다. 휴리스틱으로 의미적 정확성을 입증하지는 않습니다.'),
    finding(5, 'repair_draft', 'Atomic graph rebuild', '그래프 재구축 원자성',
            'Invalid rebuilds preserve the previous graph rather than exposing partial state.',
            '재구축 실패 시 부분 상태를 노출하지 않고 기존 그래프를 보존합니다.'),
    finding(6, 'external_evidence_required', 'Epic effective FHIR IDs', 'Epic 실제 FHIR 식별자',
            'The Nov 6 read-only sandbox check still returned a 66-character ID. Keep strict FHIR validation; vendor-effective configuration remains unresolved.',
            '11월 6일 읽기 전용 샌드박스 검사에서도 66자 식별자가 반환되었습니다. 엄격한 FHIR 검증을 유지하며 실제 공급자 설정 문제는 미해결입니다.'),
    finding(7, 'partial_repair', 'Risk ranking calibration', '위험 순위 보정',
            'Unrelated event counts no longer reduce trigger uncertainty. Failure priors and actionability remain uncalibrated heuristics requiring local clinical evaluation.',
            '관련 없는 이벤트 수로 유발 근거의 불확실성이 낮아지지 않습니다. 실패 사전값과 실행 가능성은 현지 임상 평가가 필요한 미보정 휴리스틱입니다.'),
    finding(8, 'bounded_capability', 'Report coverage and length', '보고서 범위와 길이',
            'Whole model input is limited to 6000 UTF-8 bytes; no silent truncation or chunking. OCR, image pixels, waveforms and all report types are not clinically validated.',
            '모델 입력 전체는 UTF-8 6000바이트로 제한되며 자동 잘라내기·분할을 하지 않습니다. OCR, 영상 화소, 파형 및 모든 보고서 유형의 임상 검증은 완료되지 않았습니다.'),
    finding(9, 'repair_draft', 'Patient and practice state', '환자 및 연습 상태',
            'Hide stale patient graphs, ignore superseded requests, preserve language/theme and provide a confirmed browser-only practice reset.',
            '이전 환자 그래프를 숨기고 대체된 요청을 무시하며 언어·테마를 유지합니다. 확인 절차가 있는 브라우저 전용 연습 초기화를 제공합니다.'),
    finding(10, 'repair_draft', 'Deadline illustration claims', '기한 예시 표현',
            'Label synthetic deadline arithmetic as an illustration, without claiming formal safety or proven clinical completion.',
            '합성 기한 계산을 예시로 표시하며 형식적 안전성이나 입증된 임상적 완료를 주장하지 않습니다.'),
    finding(11, 'external_evidence_required', 'Hospital deployment assurance', '병원 배포 보증',
            'Institutional access scope, SSO, TLS, encrypted storage, restore drills, independent audit anchoring, security review and local clinical release approval remain site obligations. Urgent communication follows hospital procedures.',
            '기관 접근 범위, 통합 인증, TLS, 암호화 저장, 복구 훈련, 독립 감사 앵커, 보안 검토와 현지 임상 출시 승인이 필요합니다. 긴급 연락은 병원 절차를 따릅니다.'),
    finding(12, 'repair_draft', 'Version-bound evidence', '버전에 연결된 근거',
            'This candidate status is bound to exact software bytes. Older measurements below retain their original dates and scope.',
            '이 후보 상태는 정확한 소프트웨어 바이트에 연결됩니다. 아래의 이전 측정값은 원래 날짜와 범위를 유지합니다.'),
]


def build(root: Path, test_xml=None, tested_digest=None) -> dict:
    digest = source_digest(root)
    tests = None
    if test_xml:
        if tested_digest != digest:
            raise ValueError('Tested source does not match current source')
        suites = ET.parse(test_xml).getroot()
        suites = [suites] if suites.tag == 'testsuite' else list(suites.findall('testsuite'))
        tests = {key: sum(int(s.get(key, 0)) for s in suites)
                 for key in ('tests', 'failures', 'errors', 'skipped')}
        if not tests['tests'] or tests['failures'] or tests['errors']:
            raise ValueError('A successful non-empty test receipt is required')
        tests['scope'] = 'Software regression only; not independently adjudicated clinical performance'
    return {'schema_version': 1, 'candidate': '2026-11-06 safety repair draft',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'source_sha256': digest, 'clinical_use_authorized': False,
            'independent_clinical_validation': 'pending', 'software_tests': tests,
            'findings': FINDINGS}


def check(root: Path, status: dict) -> None:
    if (status.get('schema_version') != 1 or status.get('source_sha256') != source_digest(root)
            or status.get('clinical_use_authorized') is not False
            or status.get('independent_clinical_validation') != 'pending'
            or status.get('findings') != FINDINGS):
        raise ValueError('Candidate status is stale or misstates the recorded safety scope')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', type=Path)
    parser.add_argument('--test-xml', type=Path)
    parser.add_argument('--tested-source-digest')
    parser.add_argument('--digest', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.digest:
        print(source_digest(root))
    elif args.check:
        check(root, json.loads(args.check.read_text()))
        print('Candidate provenance matches; clinical authorization remains absent.')
    elif args.output:
        args.output.write_text(json.dumps(build(root, args.test_xml, args.tested_source_digest),
                                         ensure_ascii=False, indent=2) + '\n')
    else:
        parser.error('Choose --digest, --check or --output')


if __name__ == '__main__':
    main()
