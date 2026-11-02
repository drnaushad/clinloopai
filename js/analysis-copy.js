/** Display labels only. The engine result remains available unchanged in the source section. */
(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./interface-language.js'));
  else root.ClinLoopAnalysisCopy=factory(root.ClinLoopUI);
})(typeof window==='undefined'?this:window,function(ui){
  'use strict';
  const events = { patient_notification: '환자 통보', followup_appointment: '추적 외래', followup_ct: '추적 CT', specialist_referral: '전문의 의뢰',
      biopsy_order: '조직검사 오더', colposcopy_referral: '질확대경 의뢰', callback: '환자 연락', inr_recheck: 'INR 재검',
      referral_visit: '의뢰 진료', followup_lab: '모니터링 검사', provider_review: '의료진 확인', hba1c_recheck: '당화혈색소 재검',
      culture_result: '혈액배양 재검', echocardiogram: '심초음파', colonoscopy: '대장내시경', breast_biopsy: '유방 조직검사',
      critical_value_notification: '의료진 보고', bp_check: '혈압 측정', postpartum_glucose_test: '산후 당부하검사',
      hcv_rna_test: 'HCV RNA 검사', liver_imaging: '간 영상검사', mental_health_followup: '정신건강 추적 진료',
      imaging_ct: 'CT', imaging_mri: 'MRI', imaging_ultrasound: '초음파', imaging_xray: 'X선 촬영', imaging_pet: 'PET/CT',
      endoscopic_ultrasound: '내시경초음파', biopsy_result: '조직검사 시행', pathology_result: '병리 결과',
      ai_finding_reviewed: '영상의학과 재검토 기록' };
  Object.assign(events,{lab_result:'검사 결과',radiology_report:'영상 판독',medication_change:'약물 변경',
    medication_start:'약물 시작',discharge:'퇴원',pathology_report:'병리 보고',diagnosis:'진단',
    encounter:'진료',clinical_note:'임상 기록',imaging_ai_finding:'영상 인공지능 소견'});
  function eventLabel(code,lang){
    if(lang==='ko')return events[code]||'임상 이벤트 (원문 근거 확인)';
    return String(code).replace(/_/g,' ').replace(/\bfollowup\b/g,'follow-up')
      .replace(/\b(ct|mri|pet|inr|hba1c|hcv)\b/gi,x=>x.toUpperCase());
  }
  function ruleName(name,id,lang){
    const translated=ui.translate(name,lang);
    return lang==='ko'&&translated===name&&!/[가-힣]/.test(name)?`규칙 ${id} (원문 근거 확인)`:translated;
  }
  function missingText(text,lang){
    if(lang!=='ko')return text;
    const m=String(text).match(/^Missing: (.+) within (\d+(?:\.\d+)?) (days?|hours?|minutes?)$/);
    if(!m)return '미완료 조치의 원문 근거를 확인하세요.';
    const parts=m[1].split(/(, | or )/).map(x=>x===' or '?' 또는 ':x===', '?', ':eventLabel(x,lang));
    const unit=m[3].startsWith('day')?'일':m[3].startsWith('hour')?'시간':'분';
    return `미완료: ${parts.join('')} (${m[2]}${unit} 이내)`;
  }
  function actionText(text,lang){
    if(lang!=='ko')return text;
    const value=String(text), review=value.startsWith('Human review required: ');
    const prefix=review?'사람 검토 필요. ':'';
    if(value.includes('URGENT:'))return prefix+'긴급: 기한이 지났습니다. 즉시 확인하고 조치하세요.';
    if(value.includes('HIGH PRIORITY:'))return prefix+'높은 우선순위: 오늘 확인하고 조치하세요.';
    if(value.includes('Schedule action soon'))return prefix+'후속 조치를 곧 예약하세요.';
    if(value.includes('Monitor —'))return prefix+'추적 중인 조치의 진행 상황을 확인하세요.';
    return '사람 검토 필요: 원문 근거와 추적 조치를 확인하세요.';
  }
  return {eventLabel,ruleName,missingText,actionText};
});
