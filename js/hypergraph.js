/**
 * Dynamic Temporal Hypergraph (DTH) Visualizer 2.0
 * Features medical iconography, dynamic multi-way splines, and animated particle flows.
 */

class HypergraphVisualizer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.svg = document.getElementById('hypergraph-svg');
    this.currentScenario = null;
    this.isClosedOverride = false;
    this.simulatedDays = null;
    this.nodes = [];
    this.hyperedge = null;

    if (window.ResizeObserver && this.container) {
      this.resizeObserver = new ResizeObserver(() => {
        if (this.currentScenario) {
          this.render(this.currentScenario, this.isClosedOverride, this.simulatedDays);
        }
      });
      this.resizeObserver.observe(this.container);
    }
  }

  render(scenario, isClosedOverride = false, simulatedDays = null) {
    this.currentScenario = scenario;
    this.isClosedOverride = isClosedOverride;
    this.simulatedDays = simulatedDays;
    this.svg.innerHTML = '';
    
    const rect = this.container.getBoundingClientRect();
    const width = Math.max(rect.width || this.container.clientWidth || 900, 720);
    const height = Math.max(rect.height || this.container.clientHeight || 460, 360);
    this.svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    this._injectDefs();

    const events = [...scenario.events];
    let isClosed = (scenario.ground_truth_status === 'closed') || isClosedOverride;

    if (isClosedOverride && scenario.ground_truth_status !== 'closed') {
      events.push({
        event_id: 'EVT-SIM-CLOSE',
        patient_id: scenario.patient_id,
        event_type: 'closure_action',
        timestamp: '2026-09-17T15:00:00',
        details: {
          action: scenario.missing_followup || 'Clinical follow-up completed',
          resolved_by: 'ClinLoop Proactive Alert',
          verified: true
        },
        status: 'completed'
      });
    }

    // Determine total slots along the temporal axis
    const hasGhost = !isClosed && Boolean(scenario.missing_followup);
    const totalSlots = events.length + (hasGhost ? 1 : 0);

    const paddingLeft = Math.max(120, width * 0.12);
    const paddingRight = Math.max(120, width * 0.12);
    const availableWidth = width - (paddingLeft + paddingRight);
    const stepX = totalSlots > 1 ? availableWidth / (totalSlots - 1) : availableWidth / 2;
    const centerY = height * 0.52;

    // Draw background time axis with graduation marks
    this._drawTimelineAxis(width, centerY, paddingLeft - 40, width - paddingRight + 40);

    // Position event nodes
    this.nodes = events.map((evt, idx) => {
      const x = paddingLeft + (idx * stepX);
      const yOffset = (events.length > 2 && idx % 2 === 1) ? 20 : -10;
      const y = centerY + yOffset;
      return { ...evt, x, y, index: idx };
    });

    // Draw Ghost / Unfulfilled Obligation node if open
    let ghostNode = null;
    if (hasGhost) {
      const ghostX = paddingLeft + (totalSlots - 1) * stepX;
      const ghostY = centerY - 10;
      ghostNode = {
        event_id: 'EVT-MISSING',
        patient_id: scenario.patient_id,
        event_type: 'missing_obligation',
        timestamp: 'PENDING ACTION',
        details: {
          action: scenario.missing_followup,
          hazard_status: 'Unfulfilled Clinical Obligation',
          deadline: 'Safety Clock Expired'
        },
        x: ghostX,
        y: ghostY,
        isGhost: true
      };
    }

    // Draw connecting sequence flow line
    this._drawSequenceLines(this.nodes);

    // Draw Arching Temporal Hyperedge
    this._drawHyperedge(this.nodes, ghostNode, isClosed, scenario, simulatedDays, centerY, height);

    // Draw Nodes with Icons
    this.nodes.forEach(node => this._drawNode(node));
    if (ghostNode) {
      this._drawGhostNode(ghostNode);
    }
  }

  _injectDefs() {
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
      <filter id="glow-cyan" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDeviation="6" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <filter id="glow-crimson" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDeviation="8" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <filter id="glow-emerald" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDeviation="7" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <linearGradient id="edge-grad-open" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#00f0ff" />
        <stop offset="60%" stop-color="#f59e0b" />
        <stop offset="100%" stop-color="#ff2a5f" />
      </linearGradient>
      <linearGradient id="edge-grad-closed" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#00f0ff" />
        <stop offset="100%" stop-color="#05df72" />
      </linearGradient>
    `;
    this.svg.appendChild(defs);
  }

  _drawTimelineAxis(width, centerY, startX, endX) {
    const axisGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    axisGroup.setAttribute('class', 'timeline-axis');

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', startX);
    line.setAttribute('y1', centerY);
    line.setAttribute('x2', endX);
    line.setAttribute('y2', centerY);
    line.setAttribute('stroke', 'rgba(255, 255, 255, 0.12)');
    line.setAttribute('stroke-width', '1.5');
    line.setAttribute('stroke-dasharray', '6 6');
    axisGroup.appendChild(line);

    // Axis Title
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', startX);
    text.setAttribute('y', centerY - 20);
    text.setAttribute('fill', '#64748b');
    text.setAttribute('font-size', '9.5');
    text.setAttribute('font-weight', '700');
    text.setAttribute('letter-spacing', '0.08em');
    text.setAttribute('font-family', 'var(--font-mono)');
    text.textContent = 'NEURO-SYMBOLIC TEMPORAL OBLIGATION AXIS';
    axisGroup.appendChild(text);

    this.svg.appendChild(axisGroup);
  }

  _drawSequenceLines(nodes) {
    for (let i = 0; i < nodes.length - 1; i++) {
      const n1 = nodes[i];
      const n2 = nodes[i + 1];
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const dx = (n2.x - n1.x) / 2;
      const d = `M ${n1.x} ${n1.y} C ${n1.x + dx} ${n1.y}, ${n2.x - dx} ${n2.y}, ${n2.x} ${n2.y}`;
      path.setAttribute('d', d);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', 'rgba(0, 240, 255, 0.32)');
      path.setAttribute('stroke-width', '2');
      this.svg.appendChild(path);
    }
  }

  _drawHyperedge(nodes, ghostNode, isClosed, scenario, simulatedDays, centerY, height) {
    if (nodes.length === 0) return;
    const trigger = nodes[0];
    const target = isClosed ? nodes[nodes.length - 1] : ghostNode;
    if (!target) return;

    const midX = (trigger.x + target.x) / 2;
    const arcHeight = Math.min(130, Math.max(75, centerY * 0.55));
    const arcY = Math.min(trigger.y, target.y) - arcHeight;

    const d = `M ${trigger.x} ${trigger.y - 12} Q ${midX} ${arcY} ${target.x} ${target.y - 12}`;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('fill', 'none');

    if (isClosed) {
      path.setAttribute('stroke', 'url(#edge-grad-closed)');
      path.setAttribute('class', 'hyperedge-closed');
      path.setAttribute('stroke-width', '3');
    } else {
      path.setAttribute('stroke', 'url(#edge-grad-open)');
      path.setAttribute('class', 'hyperedge-open');
      path.setAttribute('stroke-width', '2.5');
      path.setAttribute('stroke-dasharray', '8 6');
    }
    this.svg.appendChild(path);

    // Hyperedge Label badge
    const badgeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    badgeGroup.setAttribute('transform', `translate(${midX}, ${arcY + 16})`);

    const labelText = isClosed 
      ? '✓ TEMPORAL OBLIGATION CLOSED & VERIFIED' 
      : `⚠ OPEN HYPEREDGE: [${scenario.applicable_rule_id}] ${scenario.missing_followup ? scenario.missing_followup.split(' within')[0] : 'ACTION REQUIRED'}`;

    const badgeWidth = Math.max(240, labelText.length * 7.5 + 30);
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', `${-badgeWidth / 2}`);
    rect.setAttribute('y', '-14');
    rect.setAttribute('width', `${badgeWidth}`);
    rect.setAttribute('height', '28');
    rect.setAttribute('rx', '14');
    rect.setAttribute('fill', isClosed ? 'rgba(5, 223, 114, 0.18)' : 'rgba(255, 42, 95, 0.22)');
    rect.setAttribute('stroke', isClosed ? '#05df72' : '#ff2a5f');
    rect.setAttribute('stroke-width', '1.5');
    badgeGroup.appendChild(rect);

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('y', '4');
    label.setAttribute('fill', isClosed ? '#05df72' : '#ff4d79');
    label.setAttribute('font-size', '10.5');
    label.setAttribute('font-weight', '700');
    label.setAttribute('font-family', 'var(--font-mono)');
    label.textContent = labelText;
    badgeGroup.appendChild(label);

    this.svg.appendChild(badgeGroup);
  }

  _drawNode(node) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'event-node');
    g.setAttribute('transform', `translate(${node.x}, ${node.y})`);
    g.style.cursor = 'pointer';

    const isTrigger = (node.index === 0);
    const isClosure = (node.event_id === 'EVT-SIM-CLOSE');

    // Outer Halo Ring
    const outerRing = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    outerRing.setAttribute('r', isTrigger ? '24' : '20');
    outerRing.setAttribute('fill', 'rgba(7, 12, 24, 0.95)');
    outerRing.setAttribute('stroke', isClosure ? '#05df72' : (isTrigger ? '#00f0ff' : '#64748b'));
    outerRing.setAttribute('stroke-width', '2');
    outerRing.setAttribute('filter', isClosure ? 'url(#glow-emerald)' : (isTrigger ? 'url(#glow-cyan)' : 'none'));
    g.appendChild(outerRing);

    // Inner Medical Icon
    const iconText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    iconText.setAttribute('text-anchor', 'middle');
    iconText.setAttribute('y', '5');
    iconText.setAttribute('font-size', '13');
    iconText.textContent = this._getEventIcon(node.event_type);
    g.appendChild(iconText);

    // Event title label
    const textTitle = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    textTitle.setAttribute('y', '38');
    textTitle.setAttribute('text-anchor', 'middle');
    textTitle.setAttribute('fill', isClosure ? '#05df72' : '#f8fafc');
    textTitle.setAttribute('font-size', '11.5');
    textTitle.setAttribute('font-weight', '700');
    textTitle.textContent = this._formatEventType(node.event_type);
    g.appendChild(textTitle);

    // Date sublabel
    const textDate = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    textDate.setAttribute('y', '52');
    textDate.setAttribute('text-anchor', 'middle');
    textDate.setAttribute('fill', '#94a3b8');
    textDate.setAttribute('font-size', '9.5');
    textDate.setAttribute('font-family', 'var(--font-mono)');
    textDate.textContent = node.timestamp.split('T')[0] || node.timestamp;
    g.appendChild(textDate);

    // Tooltip interaction
    g.addEventListener('mouseenter', () => this._showTooltip(node));
    g.addEventListener('mouseleave', () => this._hideTooltip());

    this.svg.appendChild(g);
  }

  _drawGhostNode(node) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'ghost-node');
    g.setAttribute('transform', `translate(${node.x}, ${node.y})`);

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', '26');
    circle.setAttribute('fill', 'rgba(255, 42, 95, 0.08)');
    circle.setAttribute('stroke', '#ff2a5f');
    circle.setAttribute('stroke-width', '2');
    circle.setAttribute('stroke-dasharray', '5 4');
    circle.setAttribute('filter', 'url(#glow-crimson)');
    g.appendChild(circle);

    const textIcon = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    textIcon.setAttribute('y', '5');
    textIcon.setAttribute('text-anchor', 'middle');
    textIcon.setAttribute('fill', '#ff2a5f');
    textIcon.setAttribute('font-size', '15');
    textIcon.setAttribute('font-weight', '800');
    textIcon.textContent = '⚠';
    g.appendChild(textIcon);

    const textLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    textLabel.setAttribute('y', '38');
    textLabel.setAttribute('text-anchor', 'middle');
    textLabel.setAttribute('fill', '#ff2a5f');
    textLabel.setAttribute('font-size', '11');
    textLabel.setAttribute('font-weight', '800');
    textLabel.textContent = 'UNFULFILLED GAP';
    g.appendChild(textLabel);

    const textAction = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    textAction.setAttribute('y', '52');
    textAction.setAttribute('text-anchor', 'middle');
    textAction.setAttribute('fill', '#f43f5e');
    textAction.setAttribute('font-size', '9.5');
    textAction.setAttribute('font-weight', '600');
    textAction.setAttribute('font-family', 'var(--font-mono)');
    textAction.textContent = 'OVERDUE ACTION';
    g.appendChild(textAction);

    this.svg.appendChild(g);
  }

  _getEventIcon(typeStr) {
    const iconMap = {
      lab_order: '🧪',
      lab_result: '🔬',
      imaging_order: '🩻',
      radiology_report: '🩻',
      medication_change: '💊',
      inr_recheck: '🩸',
      culture_result: '🧫',
      patient_notification: '🔔',
      specialist_referral: '🩺',
      referral_visit: '🏥',
      closure_action: '✓'
    };
    return iconMap[typeStr] || '📋';
  }

  _formatEventType(typeStr) {
    const map = {
      lab_result: 'Lab Result',
      radiology_report: 'Radiology CT',
      imaging_order: 'CT Order',
      medication_change: 'Rx Modification',
      culture_result: 'Microbiology Culture',
      patient_notification: 'Patient Notice',
      specialist_referral: 'Referral Placed',
      referral_visit: 'Specialist Visit',
      inr_recheck: 'INR Recheck',
      closure_action: 'Loop Resolved'
    };
    return map[typeStr] || typeStr.replace(/_/g, ' ').toUpperCase();
  }

  _showTooltip(node) {
    const details = JSON.stringify(node.details, null, 2);
    const tooltip = document.getElementById('node-tooltip');
    if (!tooltip) return;
    
    document.getElementById('tt-type').textContent = `${this._getEventIcon(node.event_type)} ${this._formatEventType(node.event_type)}`;
    document.getElementById('tt-time').textContent = node.timestamp;
    document.getElementById('tt-details').textContent = details;
    
    tooltip.style.display = 'block';
  }

  _hideTooltip() {
    const tooltip = document.getElementById('node-tooltip');
    if (tooltip) tooltip.style.display = 'none';
  }
}
