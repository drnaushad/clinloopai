"""Legacy hospital extractor must preserve all pages or explicitly fail."""
import io
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from src.clinloop_engine import document_reader as reader


def page(text='SYNTHETIC report', images=None):
    item = Mock(width=612, height=792, images=images or [])
    item.extract_text.return_value = text
    return item


def pdf_context(pages):
    context = Mock()
    context.__enter__ = Mock(return_value=Mock(pages=pages))
    context.__exit__ = Mock(return_value=False)
    return context


def test_overlong_pdf_is_rejected_not_truncated():
    with patch('pdfplumber.open', return_value=pdf_context([page()] * 21)):
        with pytest.raises(reader.DocumentError, match='no partial'):
            reader.extract_text(b'%PDF-synthetic')


def test_mixed_text_and_scan_reads_every_page():
    pages = [page('SYNTHETIC text page'), page('SYNTHETIC header', images=[{}])]
    with patch('pdfplumber.open', return_value=pdf_context(pages)), \
         patch.object(reader, 'ocr_available', return_value=True), \
         patch.object(reader, '_ocr_image', return_value=('SYNTHETIC scanned findings', 80)) as ocr:
        result = reader.extract_text(b'%PDF-synthetic')
    assert result['pages'] == 2 and result['method'] == 'ocr'
    assert 'text page' in result['text'] and 'scanned findings' in result['text']
    assert ocr.call_count == 1


def test_missing_ocr_or_empty_scan_does_not_return_other_pages():
    with patch('pdfplumber.open', return_value=pdf_context([page(), page('')])), \
         patch.object(reader, 'ocr_available', return_value=False):
        with pytest.raises(reader.DocumentError, match='needs OCR'):
            reader.extract_text(b'%PDF-synthetic')
    with patch('pdfplumber.open', return_value=pdf_context([page(), page('')])), \
         patch.object(reader, 'ocr_available', return_value=True), \
         patch.object(reader, '_ocr_image', return_value=('', None)):
        with pytest.raises(reader.DocumentError, match='no partial'):
            reader.extract_text(b'%PDF-synthetic')


def test_all_tiff_frames_are_read_in_order():
    stream = io.BytesIO()
    Image.new('RGB', (200, 200), 'white').save(stream, format='TIFF', save_all=True,
                                            append_images=[Image.new('RGB', (200, 200), 'black')])
    with patch.object(reader, 'ocr_available', return_value=True), \
         patch.object(reader, '_ocr_image', side_effect=[('SYNTHETIC first', 95), ('SYNTHETIC second', 85)]):
        result = reader.extract_text(stream.getvalue(), 'scan.tiff')
    assert result == {'text': 'SYNTHETIC first\nSYNTHETIC second', 'method': 'ocr', 'pages': 2, 'confidence': 90}


def test_render_limit_before_allocating_image_and_generic_errors():
    huge = page('', [{}]); huge.width = 10000; huge.height = 10000
    with patch('pdfplumber.open', return_value=pdf_context([huge])), \
         patch.object(reader, 'ocr_available', return_value=True):
        with pytest.raises(reader.DocumentError, match='rendering limit'):
            reader.extract_text(b'%PDF-synthetic')
    huge.to_image.assert_not_called()
    with patch('pdfplumber.open', side_effect=RuntimeError('SYNTHETIC_PRIVATE_TEXT')):
        with pytest.raises(reader.DocumentError) as err:
            reader.extract_text(b'%PDF-synthetic')
    assert 'SYNTHETIC_PRIVATE_TEXT' not in str(err.value)


def test_text_limit_rejects_instead_of_truncating():
    with patch('pdfplumber.open', return_value=pdf_context([page('x' * 120001)])):
        with pytest.raises(reader.DocumentError, match='nothing was truncated'):
            reader.extract_text(b'%PDF-synthetic')


def test_long_impression_keeps_its_final_recommendation():
    text = 'IMPRESSION:\n' + 'SYNTHETIC context. ' * 300 + '\nRecommendation: repeat CT in 3 months.'
    result = reader.parse_report(text)
    assert len(result['conclusion']) > 4000
    assert 'repeat CT in 3 months' in result['conclusion']
