"""Actual synthetic PDF/OCR/DICOM imports plus local-only transport boundaries."""
import base64
import io
import json
import shutil
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from src.research_file_import import import_document, ImportFailure, MAX_FILE_BYTES
from src.research_report_gateway import create_app
from tests.test_research_report_gateway import TOKEN, ORIGIN


def pdf(texts=None, image=None):
    """Small reproducible PDF fixture; no external data or optional PDF writer."""
    texts = texts or ['SYNTHETIC REPORT. No pleural effusion.']
    objects = [b'', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for text in texts:
        page_id = len(objects) + 1; stream_id = page_id + 1
        kids.append(f'{page_id} 0 R')
        escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream = ('BT /F1 16 Tf 40 700 Td ('+escaped+') Tj ET').encode()
        resources = b'/Font << /F1 3 0 R >>'
        if image:
            image_id = page_id + 2
            resources += f' /XObject << /Im0 {image_id} 0 R >>'.encode()
            stream += b' q 500 0 0 180 40 450 cm /Im0 Do Q'
        objects.append(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << '+resources+b' >> /Contents '+str(stream_id).encode()+b' 0 R >>')
        objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
        if image:
            width,height,raw=image
            objects.append(f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(raw)} >>\nstream\n'.encode()+raw+b'\nendstream')
    objects[0]=b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1]=('<< /Type /Pages /Count '+str(len(kids))+' /Kids ['+' '.join(kids)+'] >>').encode()
    data=bytearray(b'%PDF-1.4\n');offsets=[0]
    for number,obj in enumerate(objects,1):
        offsets.append(len(data));data.extend(f'{number} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start=len(data);data.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode())
    return bytes(data)


def photo(format='PNG'):
    from PIL import Image, ImageDraw, ImageFont
    image=Image.new('RGB',(1500,450),'white');draw=ImageDraw.Draw(image)
    # Portable Tesseract fixture using Pillow's own DejaVu lookup.
    from matplotlib import get_data_path
    font=ImageFont.truetype(str(__import__('pathlib').Path(get_data_path())/'fonts/ttf/DejaVuSans.ttf'),36)
    draw.multiline_text((45,50),'SYNTHETIC REPORT\nPotassium 4.2 mmol/L\nNo pleural effusion.',fill='black',font=font,spacing=24)
    buf=io.BytesIO();image.save(buf,format=format)
    return image,buf.getvalue()


def dicom(kind='sr',complete=True,reference=False):
    from pydicom.dataset import Dataset,FileDataset,FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian,generate_uid
    meta=FileMetaDataset();meta.TransferSyntaxUID=ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID='1.2.840.10008.5.1.4.1.1.88.11' if kind=='sr' else '1.2.840.10008.5.1.4.1.1.2'
    meta.MediaStorageSOPInstanceUID=generate_uid();meta.ImplementationClassUID=generate_uid()
    ds=FileDataset(None,{},file_meta=meta,preamble=b'\0'*128);ds.SOPClassUID=meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID=meta.MediaStorageSOPInstanceUID;ds.PatientName='SYNTHETIC_PRIVATE_NAME';ds.PatientID='SYNTHETIC_PRIVATE_ID';ds.Modality='SR' if kind=='sr' else 'CT'
    if kind=='sr':
        ds.CompletionFlag='COMPLETE' if complete else 'PARTIAL';item=Dataset();item.ValueType='TEXT';item.TextValue='No pleural effusion.'
        ds.ContentSequence=[item]
        if reference:
            item=Dataset();item.ValueType='IMAGE';ds.ContentSequence.append(item)
    buf=io.BytesIO();ds.save_as(buf,enforce_file_format=True);return buf.getvalue()


def test_pdf_keeps_all_pages_in_order_and_never_calls_a_model():
    out=import_document(pdf(['SYNTHETIC first page.','SYNTHETIC second page.']),'report.pdf')
    assert out['page_count']==2 and out['pages'][0]['method']=='pdf-text'
    assert out['text'].index('first page')<out['text'].index('second page')
    assert out['human_check_required'] and out['external_model_called'] is False


def test_pdf_over_page_limit_rejects_instead_of_returning_first_pages():
    with pytest.raises(ImportFailure,match='No partial'):import_document(pdf(['SYNTHETIC']*21),'report.pdf')


@pytest.mark.parametrize('fmt,name',[('PNG','report.png'),('JPEG','report.jpg'),('TIFF','report.tiff')])
def test_actual_report_photo_ocr_preserves_number_and_unit(fmt,name):
    out=import_document(photo(fmt)[1],name)
    assert '4.2' in out['text'] and 'mmol/L' in out['text'] and 'pleural effusion' in out['text']
    assert out['pages'][0]['method']=='ocr'


def test_scanned_page_with_searchable_header_uses_full_page_ocr():
    image,raw=photo('JPEG')
    out=import_document(pdf(['SYNTHETIC searchable heading only'],(image.width,image.height,raw)),'scan.pdf')
    assert out['pages'][0]['method']=='ocr' and '4.2' in out['text'] and 'mmol/L' in out['text']


def test_multi_frame_tiff_keeps_every_frame():
    from PIL import ImageDraw
    first,_=photo();second=first.copy();ImageDraw.Draw(second).text((40,350),'SECOND FRAME',fill='black')
    buf=io.BytesIO();first.save(buf,format='TIFF',save_all=True,append_images=[second])
    out=import_document(buf.getvalue(),'multi.tiff');assert out['page_count']==2


def test_missing_ocr_language_does_not_silently_use_another(monkeypatch):
    monkeypatch.setattr('pytesseract.get_languages',lambda **_:['eng'])
    with pytest.raises(ImportFailure,match='not installed'):import_document(photo()[1],'report.png','kor+eng')


def test_sr_preserves_text_without_exporting_identity_headers():
    out=import_document(dicom(),'report.dcm')
    assert out['kind']=='dicom-sr' and out['text_review_allowed']
    assert out['text']=='No pleural effusion.'
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(out)


@pytest.mark.parametrize('changes',[{'complete':False},{'reference':True},{'kind':'image'}])
def test_dicom_images_and_incomplete_or_referenced_sr_are_preview_only(changes):
    out=import_document(dicom(**changes),'report.dcm')
    assert not out['text_review_allowed'] and 'notice' in out
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(out)


@pytest.mark.parametrize('content,name',[(b'','empty.pdf'),(b'x'*100,'bad.pdf'),(b'not png','report.png'),(b'<svg>unsafe</svg>','report.svg'),(b'x'*(MAX_FILE_BYTES+1),'large.pdf'),(b'x'*200,'bad.dcm')])
def test_bad_files_fail_without_reflecting_source(content,name):
    with pytest.raises(ImportFailure) as error:import_document(content,name)
    assert 'not png' not in str(error.value) and 'unsafe' not in str(error.value)


def gateway(enabled=True,peer='127.0.0.1'):
    transport=Mock();app=create_app({'token':TOKEN,'origin':ORIGIN,'local_setup':enabled},transport)
    return TestClient(app,base_url='http://127.0.0.1:18127',client=(peer,55000),headers={'Origin':ORIGIN,'Authorization':'Bearer '+TOKEN}),transport


def upload(**changes):
    return {'extension':'pdf','content_base64':base64.b64encode(pdf()).decode(),'synthetic_only':True,'local_processing_allowed':True,**changes}


def test_real_worker_import_requires_no_provider_key_and_never_contacts_provider():
    c,transport=gateway();r=c.post('/review/files/import',json=upload())
    assert r.status_code==200,r.text
    assert 'SYNTHETIC REPORT' in ' '.join(r.json()['text'].split()) and r.json()['external_model_called'] is False
    assert r.headers['cache-control']=='no-store';transport.post.assert_not_called()


@pytest.mark.parametrize('changes',[{'synthetic_only':False},{'local_processing_allowed':False},{'synthetic_only':'true'},{'extension':'exe'},{'content_base64':'!!!!'},{'provider':'openai'}])
def test_import_requires_exact_shape_and_explicit_local_consent(changes):
    c,transport=gateway();r=c.post('/review/files/import',json=upload(**changes));assert r.status_code in (403,422);transport.post.assert_not_called()


@pytest.mark.parametrize('enabled,peer,headers',[(False,'127.0.0.1',{}),(True,'192.168.1.5',{}),(True,'127.0.0.1',{'Authorization':''}),(True,'127.0.0.1',{'Origin':'https://evil.test'})])
def test_file_import_is_opt_in_authenticated_and_loopback_only(enabled,peer,headers):
    c,transport=gateway(enabled,peer);assert c.post('/review/files/import',headers=headers,json=upload()).status_code in (401,403);transport.post.assert_not_called()


def test_worker_failure_never_reflects_parser_errors(monkeypatch):
    def fail(*a,**k):raise subprocess.TimeoutExpired('SYNTHETIC_PRIVATE_NAME',90)
    monkeypatch.setattr('src.research_report_gateway.subprocess.run',fail)
    c,transport=gateway();r=c.post('/review/files/import',json=upload())
    assert r.status_code==422 and 'SYNTHETIC_PRIVATE' not in r.text;transport.post.assert_not_called()


def test_binary_size_cap_is_checked_before_a_parser_starts(monkeypatch):
    called=Mock();monkeypatch.setattr('src.research_report_gateway.subprocess.run',called)
    c,_=gateway();r=c.post('/review/files/import',json=upload(content_base64=base64.b64encode(b'x'*(MAX_FILE_BYTES+1)).decode()))
    assert r.status_code in (413,422);called.assert_not_called()


def test_dicom_encapsulated_pdf_extracts_complete_text():
    import pydicom
    ds=pydicom.dcmread(io.BytesIO(dicom(kind='image')))
    ds.SOPClassUID='1.2.840.10008.5.1.4.1.1.104.1';ds.file_meta.MediaStorageSOPClassUID=ds.SOPClassUID
    ds.MIMETypeOfEncapsulatedDocument='application/pdf';ds.EncapsulatedDocument=pdf(['SYNTHETIC embedded report.'])
    buf=io.BytesIO();ds.save_as(buf,enforce_file_format=True)
    out=import_document(buf.getvalue(),'report.dcm')
    assert out['kind']=='dicom-pdf' and 'embedded report' in ' '.join(out['text'].split()) and out['text_review_allowed']


def test_sr_numeric_values_keep_their_original_units():
    import pydicom
    from pydicom.dataset import Dataset
    ds=pydicom.dcmread(io.BytesIO(dicom()));item=Dataset();item.ValueType='NUM';measurement=Dataset();measurement.NumericValue='6.2'
    unit=Dataset();unit.CodeValue='mm';unit.CodingSchemeDesignator='UCUM';unit.CodeMeaning='millimeter';measurement.MeasurementUnitsCodeSequence=[unit];item.MeasuredValueSequence=[measurement]
    ds.ContentSequence.append(item);buf=io.BytesIO();ds.save_as(buf,enforce_file_format=True)
    out=import_document(buf.getvalue(),'report.dcm');assert '6.2 mm' in out['text'] and out['text_review_allowed']


def test_parser_worker_does_not_inherit_provider_or_gateway_secrets(monkeypatch):
    for key in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','CLINLOOP_RESEARCH_GATEWAY_TOKEN']:
        monkeypatch.setenv(key,'synthetic-private-sentinel')
    runner=Mock(return_value=subprocess.CompletedProcess([],0,b'{"ok":false,"detail":"File processing failed."}'))
    monkeypatch.setattr('src.research_report_gateway.subprocess.run',runner)
    c,transport=gateway();assert c.post('/review/files/import',json=upload()).status_code==422
    assert 'synthetic-private-sentinel' not in json.dumps(runner.call_args.kwargs['env'])
    assert runner.call_args.kwargs['stderr']==subprocess.DEVNULL
    transport.post.assert_not_called()
