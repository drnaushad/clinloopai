/**
 * Safety Clock & Sigmoid Risk Curve Visualizer
 * High-precision medical instrumentation for ClinLoop AI telemetry.
 */

class SafetyClockGauge {
  constructor(dialCanvasId, curveCanvasId) {
    this.dialCanvas = document.getElementById(dialCanvasId);
    this.dialCtx = this.dialCanvas.getContext('2d');
    
    this.curveCanvas = document.getElementById(curveCanvasId);
    this.curveCtx = this.curveCanvas ? this.curveCanvas.getContext('2d') : null;

    this.currentScore = 0;
    this.targetScore = 0;
    this.animating = false;

    // Sigmoid parameters
    this.k = 8.0;              // Steepness factor
    this.severityWeight = 1.0; // S multiplier
    this.tElapsed = 30;        // Current simulated days
    this.tCrit = 30;           // Critical deadline days
  }

  setScenarioParams(score, severity, ruleId, deadlineDays = 30, elapsedDays = 35) {
    this.tCrit = Math.max(1, deadlineDays);
    this.tElapsed = elapsedDays;
    
    const sevMap = { low: 0.4, moderate: 0.7, high: 0.88, critical: 1.0 };
    this.severityWeight = sevMap[severity.toLowerCase()] || 0.85;

    this.setScore(score, true);
  }

  updateTimeScrub(days) {
    this.tElapsed = days;
    // Compute sigmoid risk formula: R(t) = S * (1 / (1 + exp(-k * (t - T_crit) / T_crit)))
    const normalizedDelta = (this.tElapsed - this.tCrit) / this.tCrit;
    const sigmoid = 1 / (1 + Math.exp(-this.k * normalizedDelta));
    const calculatedRisk = Math.min(1.0, Math.max(0.0, this.severityWeight * sigmoid));

    this.setScore(calculatedRisk, false);
    this.drawSigmoidCurve();
    return calculatedRisk;
  }

  setScore(target, animate = true) {
    this.targetScore = Math.max(0, Math.min(1, target));
    if (!animate) {
      this.currentScore = this.targetScore;
      this.drawDial();
      this.drawSigmoidCurve();
    } else {
      this._startAnimation();
    }
  }

  _startAnimation() {
    if (this.animating) return;
    this.animating = true;

    const step = () => {
      const diff = this.targetScore - this.currentScore;
      if (Math.abs(diff) < 0.008) {
        this.currentScore = this.targetScore;
        this.drawDial();
        this.drawSigmoidCurve();
        this.animating = false;
      } else {
        this.currentScore += diff * 0.14;
        this.drawDial();
        this.drawSigmoidCurve();
        requestAnimationFrame(step);
      }
    };
    requestAnimationFrame(step);
  }

  drawDial() {
    const ctx = this.dialCtx;
    const width = this.dialCanvas.width;
    const height = this.dialCanvas.height;
    ctx.clearRect(0, 0, width, height);

    const centerX = width / 2;
    const centerY = height - 16;
    const radius = Math.min(centerX - 24, centerY - 8);

    // Track arc (Background)
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, Math.PI, 0, false);
    ctx.lineWidth = 14;
    const isDark = document.body.classList.contains('dark-theme');
    ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Colored Active Gauge Arc
    const score = this.currentScore;
    const endAngle = Math.PI + (score * Math.PI);

    let color = '#05df72';
    if (score > 0.7) color = '#ff2a5f';
    else if (score > 0.3) color = '#f59e0b';

    if (score > 0.01) {
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, Math.PI, endAngle, false);
      ctx.lineWidth = 14;
      ctx.strokeStyle = color;
      ctx.lineCap = 'round';
      ctx.shadowBlur = 18;
      ctx.shadowColor = color;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    // Dial Tick Marks
    for (let i = 0; i <= 20; i++) {
      const angle = Math.PI + (i / 20) * Math.PI;
      const isMajor = i % 5 === 0;
      const len = isMajor ? 8 : 4;
      const x1 = centerX + Math.cos(angle) * (radius - 12);
      const y1 = centerY + Math.sin(angle) * (radius - 12);
      const x2 = centerX + Math.cos(angle) * (radius - 12 - len);
      const y2 = centerY + Math.sin(angle) * (radius - 12 - len);

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.lineWidth = isMajor ? 1.8 : 0.9;
      ctx.strokeStyle = isMajor ? (isDark ? 'rgba(255, 255, 255, 0.35)' : '#94a3b8') : (isDark ? 'rgba(255, 255, 255, 0.12)' : '#e2e8f0');
      ctx.stroke();
    }

    // Glowing Needle
    const needleAngle = Math.PI + (score * Math.PI);
    const needleLen = radius - 6;
    const needleX = centerX + Math.cos(needleAngle) * needleLen;
    const needleY = centerY + Math.sin(needleAngle) * needleLen;

    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(needleX, needleY);
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = '#ffffff';
    ctx.shadowBlur = 10;
    ctx.shadowColor = 'rgba(255, 255, 255, 0.8)';
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Hub center
    ctx.beginPath();
    ctx.arc(centerX, centerY, 7, 0, Math.PI * 2);
    ctx.fillStyle = isDark ? '#ffffff' : '#0f172a';
    ctx.shadowBlur = 6;
    ctx.shadowColor = color;
    ctx.fill();
    ctx.shadowBlur = 0;

    // Digital Number
    const numEl = document.getElementById('risk-num-val');
    if (numEl) {
      numEl.textContent = this.currentScore.toFixed(2);
      numEl.style.color = color;
    }
  }

  drawSigmoidCurve() {
    if (!this.curveCtx || !this.curveCanvas) return;
    const ctx = this.curveCtx;
    const width = this.curveCanvas.width;
    const height = this.curveCanvas.height;
    ctx.clearRect(0, 0, width, height);

    const padLeft = 32;
    const padRight = 18;
    const padTop = 10;
    const padBottom = 22;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Axes
    ctx.beginPath();
    ctx.moveTo(padLeft, padTop);
    ctx.lineTo(padLeft, height - padBottom);
    ctx.lineTo(width - padRight, height - padBottom);
    const isDark = document.body.classList.contains('dark-theme');
    ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.15)' : '#cbd5e1';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Critical Threshold Dashed Line (y = 0.70)
    const critY = height - padBottom - (0.7 * plotH);
    ctx.beginPath();
    ctx.setLineDash([4, 4]);
    ctx.moveTo(padLeft, critY);
    ctx.lineTo(width - padRight, critY);
    ctx.strokeStyle = 'rgba(255, 42, 95, 0.4)';
    ctx.stroke();
    ctx.setLineDash([]);

    // Plot Sigmoid Curve across Days [0 -> 2 * T_crit]
    const maxDays = Math.max(60, this.tCrit * 2);
    ctx.beginPath();
    for (let px = 0; px <= plotW; px++) {
      const d = (px / plotW) * maxDays;
      const normalizedDelta = (d - this.tCrit) / this.tCrit;
      const risk = this.severityWeight * (1 / (1 + Math.exp(-this.k * normalizedDelta)));
      const py = height - padBottom - (risk * plotH);

      if (px === 0) ctx.moveTo(padLeft + px, py);
      else ctx.lineTo(padLeft + px, py);
    }

    ctx.strokeStyle = 'rgba(0, 240, 255, 0.7)';
    ctx.lineWidth = 2;
    ctx.shadowBlur = 8;
    ctx.shadowColor = 'rgba(0, 240, 255, 0.5)';
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Current Patient Tracer Dot
    const currentClampedDay = Math.min(maxDays, Math.max(0, this.tElapsed));
    const tracerPx = padLeft + (currentClampedDay / maxDays) * plotW;
    const tracerPy = height - padBottom - (this.currentScore * plotH);

    let tracerColor = '#05df72';
    if (this.currentScore > 0.7) tracerColor = '#ff2a5f';
    else if (this.currentScore > 0.3) tracerColor = '#f59e0b';

    ctx.beginPath();
    ctx.arc(tracerPx, tracerPy, 5.5, 0, Math.PI * 2);
    ctx.fillStyle = tracerColor;
    ctx.shadowBlur = 12;
    ctx.shadowColor = tracerColor;
    ctx.fill();
    ctx.shadowBlur = 0;

    // Labels
    ctx.fillStyle = '#64748b';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillText('0d', padLeft, height - 8);
    ctx.fillText(`Deadline (${this.tCrit}d)`, padLeft + (this.tCrit / maxDays) * plotW - 25, height - 8);
    ctx.fillText('1.0', 8, padTop + 10);
    ctx.fillText('0.0', 8, height - padBottom);
  }
}
