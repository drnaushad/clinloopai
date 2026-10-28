"""Bounded local-only synthetic document import. No model calls, storage or clinical rules."""
from __future__ import annotations

import hashlib
import io
import warnings
from typing import Any

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_BYTES = 120_000
MAX_PAGES = 20
MAX_PIXELS = 12_000_000


class ImportFailure(ValueError):
    """A generic import failure safe to display without source data."""


def _text(value: Any) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        raise ImportFailure('Invalid extracted text.')
    if len(value.encode('utf-8')) > MAX_TEXT_BYTES:
        raise ImportFailure('Extracted document exceeds the preview limit. Nothing was truncated.')
    return value


def _ocr(image, language: str) -> tuple[str, float | None]:
    import pytesseract
    from PIL import ImageOps
    if image.width * image.height > MAX_PIXELS:
        raise ImportFailure('Image exceeds the pixel limit.')
    installed = set(pytesseract.get_languages(config=''))
    if not set(language.split('+')).issubset(installed):
        raise ImportFailure('Selected OCR language is not installed on your local gateway.')
    image = ImageOps.autocontrast(ImageOps.grayscale(image))
    data = pytesseract.image_to_data(image, lang=language, config='--psm 6',
                                    output_type=pytesseract.Output.DICT, timeout=20)
    lines: dict[tuple, list[str]] = {}
    confidence = []
    for i, word in enumerate(data['text']):
        if not str(word).strip():
            continue
        key = tuple(data[k][i] for k in ['page_num', 'block_num', 'par_num', 'line_num'])
        lines.setdefault(key, []).append(str(word))
        score = float(data['conf'][i])
        if score >= 0:
            confidence.append(score)
    return '\n'.join(' '.join(words) for words in lines.values()), (
        round(sum(confidence) / len(confidence), 1) if confidence else None)


def _pdf(content: bytes, language: str) -> list[dict]:
    import pdfplumber
    pages = []
    total_pixels = 0
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if not 1 <= len(pdf.pages) <= MAX_PAGES:
            raise ImportFailure('PDF exceeds 20 pages. No partial document was loaded.')
        for number, page in enumerate(pdf.pages, 1):
            text = '\n'.join(line.rstrip() for line in (page.extract_text(layout=True) or '').splitlines()).strip('\n')
            method, confidence = 'pdf-text', None
            # An image-bearing page may contain a scan plus a short searchable header.
            # OCR the full page instead of accepting that header as the complete report.
            if page.images or not text.strip():
                pixels = int(page.width * 200 / 72) * int(page.height * 200 / 72)
                total_pixels += pixels
                if pixels > MAX_PIXELS or total_pixels > 48_000_000:
                    raise ImportFailure('PDF exceeds the rendering limit. No partial document was loaded.')
                text, confidence = _ocr(page.to_image(resolution=200).original, language)
                method = 'ocr'
            if not text.strip():
                raise ImportFailure('A page has no readable text. No partial document was loaded.')
            pages.append({'number': number, 'text': _text(text), 'method': method, 'confidence': confidence})
    return pages


def _image(content: bytes, language: str) -> list[dict]:
    from PIL import Image, ImageOps
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {'PNG', 'JPEG', 'TIFF'}:
                raise ImportFailure('Use PNG, JPEG or TIFF report images.')
            count = getattr(image, 'n_frames', 1)
            if not 1 <= count <= MAX_PAGES:
                raise ImportFailure('Image document exceeds 20 frames. Nothing was truncated.')
            pages, pixels = [], 0
            for index in range(count):
                image.seek(index)
                pixels += image.width * image.height
                if image.width * image.height > MAX_PIXELS or pixels > 48_000_000:
                    raise ImportFailure('Image exceeds the pixel limit.')
                frame = ImageOps.exif_transpose(image.copy())
                text, confidence = _ocr(frame, language)
                if not text.strip():
                    raise ImportFailure('An image has no readable text. No partial document was loaded.')
                pages.append({'number': index + 1, 'text': _text(text), 'method': 'ocr', 'confidence': confidence})
    return pages


def _dicom(content: bytes, language: str) -> dict:
    import pydicom
    if len(content) < 132 or content[128:132] != b'DICM':
        raise ImportFailure('Use a DICOM Part 10 file with its file header.')
    ds = pydicom.dcmread(io.BytesIO(content), stop_before_pixels=True, force=False)
    sop = str(ds.get('SOPClassUID', ''))
    # Never return patient identity, private tags, UIDs or free-form image descriptions.
    modality = str(ds.get('Modality', ''))
    metadata = {'modality': modality if modality in {'SR', 'CT', 'MR', 'DX', 'CR', 'US', 'MG', 'NM', 'PT', 'OT', 'SC'} else 'other'}
    if sop == '1.2.840.10008.5.1.4.1.1.104.1':
        if str(ds.get('MIMETypeOfEncapsulatedDocument', '')) != 'application/pdf':
            raise ImportFailure('DICOM encapsulated content is not a PDF.')
        pdf = bytes(ds.get('EncapsulatedDocument', b''))
        if not pdf.startswith(b'%PDF-'):
            raise ImportFailure('DICOM contains no readable encapsulated PDF.')
        return {'kind': 'dicom-pdf', 'pages': _pdf(pdf, language), 'text_review_allowed': True, 'metadata': metadata}
    if not sop.startswith('1.2.840.10008.5.1.4.1.1.88.'):
        return {'kind': 'dicom-image', 'pages': [], 'text_review_allowed': False, 'metadata': metadata,
                'notice': 'DICOM image inspected. Pixels were not decoded or analyzed. Image interpretation requires a validated imaging workflow.'}
    lines, count, complete = [], 0, str(ds.get('CompletionFlag', '')) == 'COMPLETE'
    def code(sequence) -> str:
        return str(sequence[0].get('CodeMeaning', '')) if sequence else ''
    def walk(items, depth=0):
        nonlocal count, complete
        if depth > 20:
            raise ImportFailure('DICOM report structure exceeds the import limit.')
        for item in items:
            count += 1
            if count > 1000:
                raise ImportFailure('DICOM report structure exceeds the import limit.')
            label = code(item.get('ConceptNameCodeSequence', []))
            kind = str(item.get('ValueType', ''))
            value = ''
            if kind == 'TEXT':
                value = str(item.get('TextValue', ''))
                if not value.strip(): complete = False
            elif kind == 'CODE':
                value = code(item.get('ConceptCodeSequence', []))
                if not value.strip(): complete = False
            elif kind == 'NUM':
                measurements = item.get('MeasuredValueSequence', [])
                if len(measurements) != 1:
                    complete = False
                else:
                    measurement = measurements[0]
                    units = measurement.get('MeasurementUnitsCodeSequence', [])
                    value = str(measurement.get('NumericValue', ''))
                    if not value or len(units) != 1: complete = False
                    value += ' ' + (str(units[0].get('CodeValue', '')) if units else '[unit missing]')
            elif kind != 'CONTAINER':
                complete = False
                value = '[Referenced, spatial or non-text content requires a separate workflow]'
            if label or value:
                lines.append(('  ' * depth) + (label + ': ' if label else '') + value)
                _text('\n'.join(lines))
            walk(item.get('ContentSequence', []), depth + 1)
    # Root container labels are preserved as source context.
    root_label = code(ds.get('ConceptNameCodeSequence', []))
    if root_label: lines.append(root_label)
    walk(ds.get('ContentSequence', []))
    text = _text('\n'.join(lines))
    if not text.strip(): complete = False
    return {'kind': 'dicom-sr', 'pages': [{'number': 1, 'method': 'dicom-sr', 'text': text, 'confidence': None}],
            'text_review_allowed': complete, 'metadata': metadata,
            'notice': 'DICOM SR text representation. Check all values and units against the original. Referenced images and non-text content are not interpreted.' if complete else
                      'DICOM report is incomplete or contains non-text content. Preview only; text analysis is blocked.'}


def import_document(content: bytes, filename: str, language: str = 'eng') -> dict:
    """Extract complete document text or inspect DICOM; never forward bytes to an LLM."""
    if not content or len(content) > MAX_FILE_BYTES:
        raise ImportFailure('Use a non-empty file up to 5 MB.')
    if language not in {'eng', 'kor+eng'}:
        raise ImportFailure('Choose a supported OCR language.')
    extension = filename.lower().rsplit('.', 1)[-1]
    try:
        if extension == 'pdf' and content.startswith(b'%PDF-'):
            result = {'kind': 'pdf', 'pages': _pdf(content, language), 'text_review_allowed': True}
        elif extension in {'png', 'jpg', 'jpeg', 'tif', 'tiff'}:
            result = {'kind': 'image', 'pages': _image(content, language), 'text_review_allowed': True}
        elif extension == 'dcm':
            result = _dicom(content, language)
        else:
            raise ImportFailure('Choose a PDF, PNG, JPEG, TIFF or DICOM file.')
        pages = result['pages']
        text = _text('\n\n'.join(page['text'] for page in pages))
        result.update(text=text, sha256=hashlib.sha256(content).hexdigest(), page_count=len(pages),
                      model_input_within_limit=0 < len(text.encode('utf-8')) <= 6000,
                      human_check_required=True, external_model_called=False)
        return result
    except ImportFailure:
        raise
    except ImportError:
        raise ImportFailure('File tools are not installed. Install the pinned API dependencies on your personal gateway.') from None
    except Exception:
        raise ImportFailure('File could not be read completely. Check the original; no partial document was loaded.') from None


def main() -> None:
    """Private bounded worker. Parser diagnostics are captured by its parent, never logged."""
    import json
    import os
    import sys
    try:
        for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
            os.environ[name] = '1'
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
            resource.setrlimit(resource.RLIMIT_CPU, (70, 75))
        except ImportError:
            pass  # Windows still has parent timeout, byte, page and pixel bounds.
        content = sys.stdin.buffer.read(MAX_FILE_BYTES + 1)
        result = {'ok': True, 'document': import_document(content, 'report.' + sys.argv[1], sys.argv[2])}
    except ImportFailure as error:
        result = {'ok': False, 'detail': str(error)}
    except Exception:
        result = {'ok': False, 'detail': 'File processing failed. No partial document was loaded.'}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
