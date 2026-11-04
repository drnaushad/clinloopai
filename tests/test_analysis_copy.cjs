const test=require('node:test'),assert=require('node:assert/strict');
const ui=require('../js/analysis-copy.js');
test('analysis results localize app-owned rule, event and missing-step labels',()=>{
 assert.equal(ui.ruleName('Warfarin Dose Change → INR Recheck','R007','ko'),'와파린 용량 변경 → INR 재검');
 assert.equal(ui.eventLabel('radiology_report','ko'),'영상 판독');
 assert.equal(ui.missingText('Missing: followup_ct or biopsy_order within 91 days','ko'),'미완료: 추적 CT 또는 조직검사 오더 (91일 이내)');
 assert.equal(ui.missingText('Missing: critical_value_notification within 1 hour','ko'),'미완료: 의료진 보고 (1시간 이내)');
});
test('urgency and human review remain visible in the Korean interface',()=>{
 assert.equal(ui.actionText('Human review required: URGENT: Immediately verify and act — Deadline violated','ko'),'사람 검토 필요. 긴급: 기한이 지났습니다. 즉시 확인하고 조치하세요.');
 assert.match(ui.actionText('NEEDS HUMAN REVIEW — insufficient data for automated judgment.','ko'),/사람 검토 필요/);
});
test('unsupported codes ask for review; source-bearing strings are never rewritten',()=>{
 const text='SYNTHETIC unknown source 원문';
 assert.match(ui.ruleName(text,'R999','ko'),/원문/);
 assert.match(ui.eventLabel('unknown_event','ko'),/원문 근거 확인/);
 assert.equal(ui.missingText(text,'en'),text);
 assert.equal(ui.actionText(text,'en'),text);
 const result={rule_name:'Warfarin Dose Change → INR Recheck',missing:'Missing: inr_recheck within 7 days',basis:['SYNTHETIC source 원문']};
 const before=JSON.stringify(result);ui.ruleName(result.rule_name,'R007','ko');ui.missingText(result.missing,'ko');assert.equal(JSON.stringify(result),before);
});
