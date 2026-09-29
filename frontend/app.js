// ═══════════════════════════════════════════════════════
//  PULSETECH APP.JS — Complete Frontend Engine
//  Architecture: ESP32-S3 → WebSocket Sim → TinyML Risk
//  → Dashboard → EHR → Appointments → CDSS
// ═══════════════════════════════════════════════════════

'use strict';

// ─── STATE ───────────────────────────────────────────
const STATE = {
  role: 'doctor',
  user: 'Dr. Arpit',
  riskScore: 12,
  riskLevel: 'LOW',
  ecgSpeed: 1,
  ecgGain: 1,
  histRange: '6h',
  emgShown: false,
  emgDismissed: false,
  voiceOn: false,
  theme: 'dark',
  // Buffers
  hrHistory: [],
  spo2History: [],
  tempHistory: [],
  bpHistory: [],
  riskHistory: [],
  ehrLog: [],
  alerts: [],
  appointments: [
    { name: 'Ravi Kumar', age: 58, symptom: 'Chest Pain', time: '10:30', score: 87, color: '#ff3e3e' },
    { name: 'Priya Sharma', age: 45, symptom: 'Breathlessness', time: '11:00', score: 64, color: '#ffaa00' },
    { name: 'Anil Verma', age: 32, symptom: 'Routine Checkup', time: '14:00', score: 28, color: '#3b82f6' }
  ],
  // Vital baselines (ESP32 simulation)
  hrBase: 72,
  spo2Base: 98,
  tempBase: 36.6,
  scenario: 'normal',
  scenarioTick: 0,
  ecgPhase: 0,
};

// ─── CHART INSTANCES ─────────────────────────────────
const CHARTS = {};

// ─── CHART CONFIG DEFAULTS ────────────────────────────
const CHART_BASE = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 0 },
  plugins: { legend: { display: false } },
  scales: { x: { display: false }, y: { display: false } }
};

// ═══════════════════════════════════════════════════════
//  AUTH
// ═══════════════════════════════════════════════════════
let selectedRole = 'doctor';
function pickRole(r, el) {
  selectedRole = r;
  document.querySelectorAll('.role-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function doLogin() {
  const username = document.getElementById('l-user').value.trim();
  const password = document.getElementById('l-pass').value;

  if (!username || !password) {
    notify('⚠️ Username and password required', 'warning');
    return;
  }

  notify('🔐 Authenticating...', 'info');

  const demoUsers = {
    'dr.arpit': { password: 'doctor123', name: 'Dr. Arpit', role: 'doctor' },
    'patient01': { password: 'patient123', name: 'Ravi Kumar (Patient)', role: 'patient' },
    'admin': { password: 'admin123', name: 'System Admin', role: 'admin' }
  };

  const loginSuccess = (usr, roleName, displayName, authToken) => {
    const userObj = { id: 1, username: usr, name: displayName || usr, role: roleName || selectedRole || 'doctor' };
    localStorage.setItem('pulsetech_token', authToken || 'demo-token');
    localStorage.setItem('pulsetech_user', JSON.stringify(userObj));

    STATE.role = userObj.role;
    STATE.user = userObj.name;

    const uNameEl = document.getElementById('u-name');
    if (uNameEl) uNameEl.textContent = STATE.user;
    const uRoleEl = document.getElementById('u-role');
    if (uRoleEl) uRoleEl.textContent = STATE.role.toUpperCase();
    
    const avMap = { doctor: 'DA', patient: 'PA', admin: 'SA' };
    const uAvEl = document.getElementById('u-avatar');
    if (uAvEl) uAvEl.textContent = avMap[STATE.role] || 'U';

    // Instantly remove and hide the login modal
    const loginModal = document.getElementById('login-screen');
    if (loginModal) {
      loginModal.style.setProperty('display', 'none', 'important');
      loginModal.style.pointerEvents = 'none';
      try { loginModal.remove(); } catch(e) {}
    }

    notify('👋 Welcome back, ' + STATE.user, 'success');
    try { initAllCharts(); } catch(e) { console.warn('[Chart] initAllCharts error:', e); }
    try { startDataStream(); } catch(e) { console.warn('[Data] startDataStream error:', e); }
    try { renderApptQueue(); } catch(e) {}
    try { renderAlerts(); } catch(e) {}
    try { renderApptPreview(); } catch(e) {}
  };

  // 1. If running on GitHub Pages (static), authenticate client-side directly
  if (window.location.hostname.includes('github.io') || window.location.protocol === 'file:') {
    const uLower = username.toLowerCase();
    if (demoUsers[uLower] && demoUsers[uLower].password === password) {
      loginSuccess(username, demoUsers[uLower].role, demoUsers[uLower].name);
    } else {
      loginSuccess(username, selectedRole || 'doctor', username);
    }
    return;
  }

  // 2. Otherwise try local backend server API
  fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  .then(res => {
    if (!res.ok) {
      if (res.status === 404) {
        // Fallback for static hosting
        const uLower = username.toLowerCase();
        if (demoUsers[uLower] && demoUsers[uLower].password === password) {
          loginSuccess(username, demoUsers[uLower].role, demoUsers[uLower].name);
        } else {
          loginSuccess(username, selectedRole || 'doctor', username);
        }
        return null;
      }
      return res.json().then(err => { throw new Error(err.error || 'Authentication failed'); });
    }
    return res.json();
  })
  .then(data => {
    if (!data) return;
    loginSuccess(data.user.username, data.user.role, data.user.name, data.token);
  })
  .catch(err => {
    // If backend connection fails, allow fallback demo login
    console.warn('[Auth] Server unreachable, fallback to client auth:', err.message);
    const uLower = username.toLowerCase();
    if (demoUsers[uLower] && demoUsers[uLower].password === password) {
      loginSuccess(username, demoUsers[uLower].role, demoUsers[uLower].name);
    } else {
      loginSuccess(username, selectedRole || 'doctor', username);
    }
  });
}

// ═══════════════════════════════════════════════════════
//  NAVIGATION
// ═══════════════════════════════════════════════════════
const VIEW_TITLES = {
  dashboard: 'LIVE MONITORING',
  ecg:       'ECG DIAGNOSTIC',
  history:   'HISTORICAL TRENDS',
  ehr:       'ELECTRONIC HEALTH RECORDS',
  appt:      'APPOINTMENT SYSTEM',
  ai:        'AI / TINYML ENGINE',
  alerts:    'ALERT CENTER',
  settings:  'SYSTEM SETTINGS'
};

function goView(id, el) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const v = document.getElementById('view-' + id);
  if (v) v.classList.add('active');
  if (el) el.classList.add('active');
  document.getElementById('pg-title').textContent = VIEW_TITLES[id] || 'PULSETECH';

  // Lazy-init charts on first load
  setTimeout(() => {
    if (id === 'history') buildHistChart();
    if (id === 'ai')      buildAiLiveChart();
  }, 80);
}

// ═══════════════════════════════════════════════════════
//  CHART FACTORY
// ═══════════════════════════════════════════════════════
function destroyCanvasChart(canvasId) {
  const el = document.getElementById(canvasId);
  if (el) {
    try {
      const existing = (window.Chart && Chart.getChart) ? Chart.getChart(el) : null;
      if (existing) existing.destroy();
    } catch (e) {}
  }
}

function mkLine(canvasId, color, bgColor, len = 30, yMin, yMax) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  destroyCanvasChart(canvasId);
  const opts = {
    ...JSON.parse(JSON.stringify(CHART_BASE)),
    scales: {
      x: { display: false },
      y: { display: false, min: yMin, max: yMax }
    }
  };
  return new Chart(ctx.getContext('2d'), {
    type: 'line',
    data: {
      labels: Array(len).fill(''),
      datasets: [{
        data: Array(len).fill(0),
        borderColor: color,
        backgroundColor: bgColor || 'transparent',
        borderWidth: 1.5,
        pointRadius: 0,
        fill: !!bgColor,
        tension: 0.4
      }]
    },
    options: opts
  });
}

function initAllCharts() {
  // Destroy any existing charts first to avoid Chart.js collision
  ['ecg-main', 'ecg-full', 'spark-hr', 'spark-spo2', 'spark-temp', 'spark-bp', 'overview-chart'].forEach(destroyCanvasChart);
  Object.keys(CHARTS).forEach(k => {
    if (CHARTS[k] && typeof CHARTS[k].destroy === 'function') {
      try { CHARTS[k].destroy(); } catch(e) {}
      CHARTS[k] = null;
    }
  });

  // ECG charts (tension:0 for raw waveform)
  const ecgOpts = {
    ...JSON.parse(JSON.stringify(CHART_BASE)),
    scales: { x: { display: false }, y: { display: false, min: -2.8, max: 3.5 } }
  };
  const ecgData200 = { labels: Array(220).fill(''), datasets: [{ data: Array(220).fill(0), borderColor: '#00ff88', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0 }] };
  const ecgData400 = { labels: Array(440).fill(''), datasets: [{ data: Array(440).fill(0), borderColor: '#00ff88', borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0 }] };

  const elMain = document.getElementById('ecg-main');
  if (elMain) CHARTS.ecgMain = new Chart(elMain.getContext('2d'), { type: 'line', data: ecgData200, options: ecgOpts });
  const elFull = document.getElementById('ecg-full');
  if (elFull) CHARTS.ecgFull = new Chart(elFull.getContext('2d'), { type: 'line', data: ecgData400, options: ecgOpts });

  // Spark charts
  CHARTS.sHr   = mkLine('spark-hr',   '#ef4444', 'rgba(239,68,68,.08)', 30);
  CHARTS.sSpo2 = mkLine('spark-spo2', '#3b82f6', 'rgba(59,130,246,.08)', 30);
  CHARTS.sTemp = mkLine('spark-temp', '#ffaa00', 'rgba(255,170,0,.08)', 30);
  CHARTS.sBp   = mkLine('spark-bp',   '#8b5cf6', 'rgba(139,92,246,.08)', 30);

  // 24h overview
  const elOv = document.getElementById('overview-chart');
  if (elOv) {
    const tl = Array.from({ length: 24 }, (_, i) => i + ':00');
    CHARTS.overview = new Chart(elOv.getContext('2d'), {
      type: 'line',
      data: {
        labels: tl,
        datasets: [
          { data: tl.map(() => Math.round(68 + Math.random() * 22)), borderColor: '#ef4444', borderWidth: 1.5, pointRadius: 0, fill: false, tension: .4 },
          { data: tl.map(() => Math.round(95 + Math.random() * 4)),  borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, fill: false, tension: .4 }
        ]
      },
      options: CHART_BASE
    });
  }

  // ECG AI interpretation
  try {
    renderEcgAiInterpretation([0.95, 0.02, 0.01, 0.00, 0.01, 0.01, 0.00, 0.00, 0.00, 0.00]);
  } catch(e) {}
}

function buildHistChart() {
  const ptCounts = { '6h': 72, '24h': 288, '7d': 168, '30d': 720 };
  const n = ptCounts[STATE.histRange] || 72;

  destroyCanvasChart('hist-chart');
  if (CHARTS.hist) {
    try { CHARTS.hist.destroy(); } catch(e) {}
    CHARTS.hist = null;
  }
  const elHist = document.getElementById('hist-chart');
  if (!elHist) return;
  CHARTS.hist = new Chart(elHist.getContext('2d'), {
    type: 'line',
    data: {
      labels: Array(n).fill(''),
      datasets: [
        { label: 'HR',   data: Array.from({ length: n }, () => Math.round(66 + Math.random() * 28)), borderColor: '#ef4444', borderWidth: 1.5, pointRadius: 0, fill: false, tension: .4 },
        { label: 'SpO₂', data: Array.from({ length: n }, () => Math.round(94 + Math.random() * 5)),  borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, fill: false, tension: .4 },
        { label: 'Temp', data: Array.from({ length: n }, () => +(36.3 + Math.random() * 1.2).toFixed(1)), borderColor: '#ffaa00', borderWidth: 1.5, pointRadius: 0, fill: false, tension: .4 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 0 },
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { ticks: { color: '#4a6080', font: { family: 'Space Mono', size: 8 } }, grid: { color: 'rgba(36,56,96,.4)' }, border: { display: false } }
      }
    }
  });

  // Risk timeline
  if (CHARTS.riskTl) CHARTS.riskTl.destroy();
  CHARTS.riskTl = new Chart(document.getElementById('risk-tl-chart').getContext('2d'), {
    type: 'bar',
    data: {
      labels: Array(48).fill(''),
      datasets: [{
        data: Array.from({ length: 48 }, () => Math.max(3, Math.random() * 88)),
        backgroundColor: function(c) {
          const v = c.raw;
          return v > 60 ? 'rgba(255,62,62,.65)' : v > 30 ? 'rgba(255,170,0,.6)' : 'rgba(0,255,136,.45)';
        },
        borderRadius: 2, borderSkipped: false
      }]
    },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 0 }, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
  });
}

function buildAiLiveChart() {
  if (CHARTS.aiLive) CHARTS.aiLive.destroy();
  const d = STATE.riskHistory.length > 0 ? [...STATE.riskHistory] : Array.from({ length: 60 }, () => Math.round(Math.random() * 32));
  CHARTS.aiLive = new Chart(document.getElementById('ai-live-chart').getContext('2d'), {
    type: 'line',
    data: {
      labels: Array(d.length).fill(''),
      datasets: [{ data: d, borderColor: '#7c3aed', backgroundColor: 'rgba(124,58,237,.08)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: .4 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 0 },
      plugins: { legend: { display: false } },
      scales: { x: { display: false }, y: { display: false, min: 0, max: 100 } }
    }
  });
}

// ═══════════════════════════════════════════════════════
//  ESP32 DATA SIMULATION (WebSocket-equivalent)
// ═══════════════════════════════════════════════════════

// Realistic PQRST ECG generation
function ecgSample(phase) {
  const p = phase % (2 * Math.PI);
  // P wave
  if (p < 0.26) return 0.22 * Math.sin(p / 0.26 * Math.PI);
  // PQ segment
  if (p < 0.40) return -0.05;
  // Q dip
  if (p < 0.44) return -0.12 * Math.sin((p - 0.40) / 0.04 * Math.PI);
  // R peak (dominant)
  if (p < 0.58) return 2.8 * Math.sin((p - 0.44) / 0.14 * Math.PI);
  // S dip
  if (p < 0.70) return -0.35 * Math.sin((p - 0.58) / 0.12 * Math.PI);
  // ST segment
  if (p < 0.90) return 0.02;
  // T wave
  if (p < 1.30) return 0.42 * Math.sin((p - 0.90) / 0.40 * Math.PI);
  return 0;
}

// TinyML Risk Engine (LSTM-inspired scoring)
function tinyMLRisk(hr, spo2, temp) {
  let score = 0;
  // Tachycardia / bradycardia
  if (hr > 100) score += (hr - 100) * 0.8;
  if (hr < 50)  score += (50 - hr)  * 1.2;
  // Hypoxia
  if (spo2 < 95) score += (95 - spo2) * 3.5;
  // Fever / hypothermia
  if (temp > 38.0) score += (temp - 38.0) * 4.0;
  if (temp < 36.0) score += (36.0 - temp) * 3.0;
  // LSTM trend penalty — rising HR trend
  if (STATE.hrHistory.length > 5) {
    const recent = STATE.hrHistory.slice(-6);
    const trend = recent[recent.length - 1] - recent[0];
    if (trend > 4) score += trend * 0.5;
  }
  return Math.min(100, Math.max(0, Math.round(score)));
}

function getRiskLevel(score) {
  return score > 60 ? 'HIGH' : score > 30 ? 'MEDIUM' : 'LOW';
}

function getPrediction(score, hr, spo2) {
  if (score > 60) return '🚨 CRITICAL: Patient in high-risk state. Immediate intervention required.';
  if (score > 50) return '⚠️ Patient may reach HIGH RISK in next ~10 minutes if trend persists.';
  if (score > 40) return '⚠️ Elevated risk. Possible escalation to HIGH RISK within ~25 minutes.';
  if (score > 30) return '⚡ Moderate risk detected. Monitor closely. Review in 15 min.';
  const rising = STATE.riskHistory.length > 4 &&
    STATE.riskHistory.slice(-4).every((v, i, a) => i === 0 || v >= a[i - 1]);
  if (rising) return '📈 Slow upward trend. No immediate danger — watchful monitoring advised.';
  return '✅ Vitals stable. No escalation predicted in next 60 min.';
}

function getCDSS(hr, spo2, temp, score, isFingerOn = true) {
  const items = [];
  if (!isFingerOn || hr <= 0) {
    items.push({ type: 'info', msg: '⏳ MAX30102 sensor active — awaiting patient finger placement.' });
    items.push({ type: 'info', msg: '💡 Place finger flat on the optical sensor LED to begin live AI diagnostic.' });
    return items;
  }
  if (hr > 100) items.push({ type: 'alert', msg: '⚡ Possible tachycardia — HR ' + hr + ' BPM. Review 12-lead ECG.' });
  if (hr < 55)  items.push({ type: 'alert', msg: '🔻 Bradycardia — HR ' + hr + ' BPM. Physician review needed.' });
  if (spo2 < 95) items.push({ type: 'warn',  msg: '🫁 Low SpO₂ (' + spo2 + '%). Consider supplemental O₂.' });
  if (spo2 < 90) items.push({ type: 'alert', msg: '🚨 Critical SpO₂ (' + spo2 + '%). Respiratory support required.' });
  if (temp > 38.5) items.push({ type: 'warn', msg: '🌡 Fever (' + temp.toFixed(1) + '°C). Monitor for sepsis.' });
  if (score > 60) items.push({ type: 'alert', msg: '🧠 TinyML HIGH RISK. Escalate to ICU protocol.' });
  else if (score > 30) items.push({ type: 'warn', msg: '🧠 TinyML elevated risk trend. Increase monitoring frequency.' });
  if (!items.length) {
    items.push({ type: 'info', msg: 'ℹ️ All vitals within normal parameters. Routine 15-min monitoring.' });
    if (Math.random() < 0.35) items.push({ type: 'info', msg: '💊 Medication schedule on track. Next dose scheduled 14:00.' });
  }
  return items;
}

let ws = null;
let wsReconnectDelay = 3000; // starts at 3s, backs off exponentially

function promptHardwareBridge() {
  const current = localStorage.getItem('pulsetech_bridge_host') || '';
  const input = prompt("🔗 Connect Real ESP32 Physical Sensors:\n\nEnter your running Cloudflare Tunnel URL or Server Address:\n(e.g., delivery-nvidia-tennessee-processors.trycloudflare.com or 10.149.187.17:3001)\n\nLeave empty to use simulated demo mode.", current);
  if (input !== null) {
    const trimmed = input.trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/+$/, '');
    if (trimmed === '') {
      localStorage.removeItem('pulsetech_bridge_host');
      notify('Switched to simulated demo mode', 'info');
      setTimeout(() => location.reload(), 500);
    } else {
      localStorage.setItem('pulsetech_bridge_host', trimmed);
      notify('Connecting to hardware bridge: ' + trimmed, 'info');
      STATE.demoSimMode = false;
      initWebSocket(trimmed);
    }
  }
}

const DEFAULT_BRIDGE_HOST = 'thinkpad-containers-scout-star.trycloudflare.com';

function initWebSocket(overrideHost) {
  const token = localStorage.getItem('pulsetech_token') || 'dev-token';
  const isGitHubPages = window.location.hostname.includes('github.io');
  const bridgeHost = overrideHost || localStorage.getItem('pulsetech_bridge_host') || (isGitHubPages ? DEFAULT_BRIDGE_HOST : '');
  const targetHost = bridgeHost || (isGitHubPages ? DEFAULT_BRIDGE_HOST : window.location.host);
  
  if (!targetHost) {
    console.log('[WS] Running standalone interactive simulation on GitHub Pages.');
    return;
  }

  const cleanHost = targetHost.replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/ws.*$/i, '').replace(/\/+$/, '');
  const proto = (window.location.protocol === 'https:' || cleanHost.includes('trycloudflare.com')) ? 'wss:' : 'ws:';
  const wsUrl = `${proto}//${cleanHost}/ws?token=${encodeURIComponent(token)}`;
  console.log('[WS] Connecting to:', wsUrl);
  
  try {
    if (ws) { ws.close(); }
    ws = new WebSocket(wsUrl);
  } catch (e) {
    console.warn('[WS] Error initializing WebSocket:', e);
    return;
  }
  
  ws.onopen = () => {
    console.log('[WS] Connected to backend hardware server!');
    ws.send(JSON.stringify({ type: 'AUTH', token: token }));
    wsReconnectDelay = 3000;
    notify('🔌 Connected to live ESP32 hardware (' + cleanHost + ')', 'success');
    const liveChipText = document.getElementById('live-chip-text');
    if (liveChipText) liveChipText.textContent = 'LIVE · HARDWARE';
  };
  
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);

      if (msg.type === 'DEVICE_STATUS') {
        if (!msg.is_online) {
          STATE.isHardwareOnline = false;
          if (!STATE.demoSimMode) {
            runDemoSimulation();
          }
        } else {
          STATE.isHardwareOnline = true;
        }
        return;
      }

      if (msg.type === 'VITALS' || msg.type === 'SENSOR_DATA') {
        STATE.demoSimMode = false;
        stopDemoSimulation();
        STATE.lastHardwarePacketTime = Date.now();
        STATE.isHardwareOnline = true;

        const { hr, spo2, temperature, sys_bp, dia_bp, risk_score, risk_level, ecg_sample, ecg_probabilities, risk_breakdown, recommendation, explainability } = msg;
        
        // Strict finger detection: either explicit flag or valid physiological ranges (hr >= 30, spo2 >= 50)
        const isFingerOn = (msg.finger_detected === true || (msg.finger_detected === undefined && hr >= 30 && spo2 >= 50)) && (hr >= 30);
        handleFingerSensorBanner(isFingerOn);

        const liveChipText = document.getElementById('live-chip-text');
        if (liveChipText) {
          liveChipText.textContent = isFingerOn ? 'LIVE · ESP32 HARDWARE' : 'LIVE · ESP32 (STANDBY)';
        }

        updateVitals(hr, spo2, temperature, sys_bp, dia_bp, risk_score, isFingerOn);

        if (isFingerOn) {
          const push = (arr, v, max = 250) => { arr.push(v); if (arr.length > max) arr.shift(); };
          push(STATE.hrHistory, hr);
          push(STATE.spo2History, spo2);
          push(STATE.tempHistory, temperature);
          push(STATE.bpHistory, sys_bp || 120);
          push(STATE.riskHistory, risk_score);

          updateRisk(risk_score, ecg_probabilities, risk_breakdown, recommendation);
          updateCDSS(hr, spo2, temperature, risk_score, recommendation, true);
          updateEHR(hr, spo2, temperature, risk_score, recommendation);
          renderExplainability(explainability, ecg_probabilities);
        } else {
          // No finger on sensor -> Clean Standby State (NO fake bradycardia or critical alarms!)
          updateRisk(0, [0.98, 0.01, 0.01, 0, 0, 0, 0, 0, 0, 0], null, { level: 'LOW', action: 'MAX30102 sensor active. Place finger on sensor to begin.', reasoning: 'Sensor in standby mode awaiting pulse signal.' });
          updateCDSS(0, 0, temperature, 0, null, false);
          renderExplainability(null, [0.98, 0.01, 0.01, 0, 0, 0, 0, 0, 0, 0]);
        }

        const sampleVal = isFingerOn ? parseFloat(ecg_sample || 0) : 0.50;
        if (CHARTS.ecgMain) {
          CHARTS.ecgMain.data.datasets[0].data.push(sampleVal);
          CHARTS.ecgMain.data.datasets[0].data.shift();
          CHARTS.ecgMain.update('none');
        }
        if (CHARTS.ecgFull) {
          CHARTS.ecgFull.data.datasets[0].data.push(sampleVal);
          CHARTS.ecgFull.data.datasets[0].data.shift();
          CHARTS.ecgFull.update('none');
        }
        if (CHARTS.aiLive) {
          CHARTS.aiLive.data.datasets[0].data.push(isFingerOn ? risk_score : 0);
          CHARTS.aiLive.data.datasets[0].data.shift();
          CHARTS.aiLive.update('none');
        }
        
        const aiChip = document.getElementById('ai-score-chip');
        if (aiChip) aiChip.textContent = 'SCORE: ' + (isFingerOn ? risk_score : '0');
        const aiRisk = document.getElementById('ai-risk-live');
        if (aiRisk) aiRisk.textContent = (isFingerOn ? risk_score : '0') + ' / 100';
        
        if (isFingerOn && risk_score > 60 && !STATE.emgShown && !STATE.emgDismissed) {
          triggerEmergency();
        }
        if (risk_score < 48) {
          STATE.emgShown = false;
        }
      }

      // WebRTC Call Signaling Messages
      if (['WEBRTC_OFFER', 'WEBRTC_ANSWER', 'WEBRTC_CANDIDATE', 'WEBRTC_CALL_INIT', 'WEBRTC_CALL_END'].includes(msg.type)) {
        if (msg.type === 'WEBRTC_CALL_INIT') {
          notify(`📞 Incoming WebCall from ${msg.sender_name || 'Attending Physician'}!`, 'info');
        } else if (msg.type === 'WEBRTC_CALL_END') {
          notify('📞 Call ended by remote peer', 'info');
          endWebCall();
        }
      }
    } catch (e) {
      console.error('[WS] Message parse error:', e);
    }
  };
  
  ws.onclose = (event) => {
    const token = localStorage.getItem('pulsetech_token');
    if (!token) {
      console.log('[WS] Disconnected — not reconnecting (user not logged in).');
      return;
    }
    // Exponential backoff: 3s → 6s → 12s → 24s → max 30s
    console.log(`[WS] Disconnected (code: ${event.code}), retrying in ${wsReconnectDelay / 1000}s...`);
    setTimeout(initWebSocket, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
  };
}

let streamStarted = false;

function renderOfflineState() {
  // Topbar Status Chips
  const riskChip = document.getElementById('risk-chip');
  if (riskChip) {
    riskChip.className = 'risk-chip rc-offline';
    riskChip.style.background = 'rgba(239,68,68,.12)';
    riskChip.style.border = '1px solid rgba(239,68,68,.3)';
    riskChip.style.color = 'var(--critical)';
    riskChip.textContent = '🔴 DISCONNECTED / OFFLINE';
  }

  const riskBadge = document.getElementById('risk-level-badge');
  if (riskBadge) {
    riskBadge.className = 'chip chip-r';
    riskBadge.style.textAlign = 'center';
    riskBadge.style.padding = '5px';
    riskBadge.style.borderRadius = 'var(--r)';
    riskBadge.style.marginBottom = '8px';
    riskBadge.style.fontSize = '10px';
    riskBadge.textContent = '● ESP32 OFFLINE';
  }

  // Vital Displays
  setText('hr-val', '--');
  setText('spo2-val', '--');
  setText('temp-val', '--');
  setText('bp-val', '--/--');

  setText('p-hr-val', '--');
  setText('p-spo2-val', '--');
  setText('p-temp-val', '--');
  setText('p-bp-val', '-- / --');

  setText('p-hr-desc', '🔴 Device Disconnected');
  setText('p-spo2-desc', '🔴 Awaiting ESP32 Stream');
  setText('p-temp-desc', '🔴 No Sensor Signal');
  setText('p-bp-desc', '🔴 Offline');

  setText('ecg-meta', 'OFFLINE · Lead II · Awaiting ESP32 Hardware Telemetry');
  if (document.getElementById('ecg-meta2'))
    setText('ecg-meta2', 'OFFLINE · ESP32 Hardware Disconnected');

  // Flatline ECG
  try {
    if (CHARTS.ecgMain && CHARTS.ecgMain.data && CHARTS.ecgMain.data.datasets && CHARTS.ecgMain.data.datasets[0]) {
      CHARTS.ecgMain.data.datasets[0].data = Array(220).fill(0);
      CHARTS.ecgMain.update('none');
    }
  } catch(e) {}
  try {
    if (CHARTS.ecgFull && CHARTS.ecgFull.data && CHARTS.ecgFull.data.datasets && CHARTS.ecgFull.data.datasets[0]) {
      CHARTS.ecgFull.data.datasets[0].data = Array(440).fill(0);
      CHARTS.ecgFull.update('none');
    }
  } catch(e) {}

  // Advisor Banner
  const mainMsg = document.getElementById('patient-main-msg');
  const chip = document.getElementById('patient-status-chip');
  if (chip) { chip.className = 'chip chip-r'; chip.textContent = '🔴 ESP32 OFFLINE'; }
  if (mainMsg) {
    mainMsg.style.borderLeftColor = 'var(--critical)';
    mainMsg.innerHTML = `<strong>🔴 ESP32-S3 Hardware Offline:</strong> No live sensor telemetry detected. <strong>To start monitoring:</strong> Power on your ESP32-S3 board with MAX30102 / AD8232 sensors and ensure it is transmitting data to <code>http://[SERVER_IP]:3001/api/sensor-data</code> or WebSocket <code>ws://[SERVER_IP]:3001/ws</code>.`;
  }

  const p = document.getElementById('predict-text');
  if (p) p.textContent = '📡 Device offline. Connect ESP32-S3 hardware to activate live AI monitoring.';

  setText('g-score', '--');
  const gNum = document.getElementById('g-score');
  if (gNum) gNum.style.color = 'var(--text-3)';

  const arc = document.getElementById('g-arc');
  if (arc) {
    arc.style.stroke = 'var(--wire)';
    arc.style.strokeDashoffset = 201;
  }
}

let simIntervalTimer = null;
let simEcgTimer = null;

function runDemoSimulation() {
  if (simIntervalTimer) return;
  STATE.demoSimMode = true;
  let simPhase = 0;
  simEcgTimer = setInterval(() => {
    if (!STATE.demoSimMode) { clearInterval(simEcgTimer); simEcgTimer = null; return; }
    simPhase += 0.15;
    const sampleVal = ecgSample(simPhase);
    if (CHARTS.ecgMain) {
      CHARTS.ecgMain.data.datasets[0].data.push(sampleVal);
      CHARTS.ecgMain.data.datasets[0].data.shift();
      CHARTS.ecgMain.update('none');
    }
    if (CHARTS.ecgFull) {
      CHARTS.ecgFull.data.datasets[0].data.push(sampleVal);
      CHARTS.ecgFull.data.datasets[0].data.shift();
      CHARTS.ecgFull.update('none');
    }
  }, 40);

  let simTick = 0;
  simIntervalTimer = setInterval(() => {
    if (!STATE.demoSimMode) { clearInterval(simIntervalTimer); simIntervalTimer = null; return; }
    simTick++;
    const hr = Math.round(72 + Math.sin(simTick * 0.3) * 4);
    const spo2 = 98 + Math.round(Math.random());
    const temp = +(36.6 + Math.sin(simTick * 0.1) * 0.2).toFixed(1);
    const riskScore = 12;
    updateVitals(hr, spo2, temp, 120, 80, riskScore);
    updateRisk(riskScore, [0.98, 0.01, 0.01, 0, 0, 0, 0, 0, 0, 0], { ecg: 0.2, vitals: 0.7 }, { level: 'LOW', action: 'Normal baseline physiological parameters.', reasoning: 'Sinus rhythm confirmed' });
    updateCDSS(hr, spo2, temp, riskScore, { level: 'LOW', action: 'All vitals within normal parameters.' });
    
    const liveChipText = document.getElementById('live-chip-text');
    if (liveChipText) liveChipText.textContent = 'LIVE · SIMULATION';
    const riskChip = document.getElementById('risk-chip');
    if (riskChip) {
      riskChip.className = 'risk-chip rc-low';
      riskChip.style.color = 'var(--pulse)';
      riskChip.textContent = 'LOW RISK';
    }
  }, 1000);
}

function stopDemoSimulation() {
  STATE.demoSimMode = false;
  if (simIntervalTimer) { clearInterval(simIntervalTimer); simIntervalTimer = null; }
  if (simEcgTimer) { clearInterval(simEcgTimer); simEcgTimer = null; }
}

function startDataStream() {
  if (window.location.protocol !== 'file:') {
    initWebSocket();
  }
  
  if (streamStarted) return;
  streamStarted = true;
  
  // Immediately start simulation so dashboard is active from second zero
  runDemoSimulation();

  // Watchdog timer: checks every 1s if ESP32 telemetry packet arrived within last 4.5s
  setInterval(() => {
    const now = Date.now();
    if (!STATE.lastHardwarePacketTime || (now - STATE.lastHardwarePacketTime) > 4500) {
      if (STATE.isHardwareOnline) {
        STATE.isHardwareOnline = false;
      }
      if (!STATE.demoSimMode) {
        runDemoSimulation();
      }
    }
  }, 1000);
}

// ═══════════════════════════════════════════════════════
//  DISPLAY UPDATES
// ═══════════════════════════════════════════════════════
function handleFingerSensorBanner(isFingerOn) {
  let banner = document.getElementById('finger-sensor-banner');
  if (!isFingerOn) {
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'finger-sensor-banner';
      banner.style.cssText = 'position:fixed;top:60px;left:50%;transform:translateX(-50%);background:rgba(255,170,0,0.22);border:1px solid #ffaa00;color:#ffaa00;padding:8px 24px;border-radius:24px;font-weight:700;font-size:12px;z-index:9999;box-shadow:0 6px 25px rgba(0,0,0,0.5);backdrop-filter:blur(8px);display:flex;align-items:center;gap:8px;letter-spacing:1px;pointer-events:none;';
      banner.innerHTML = '<span>⚠️</span> <span>NO FINGER DETECTED — Please place finger on MAX30102 sensor properly</span>';
      document.body.appendChild(banner);
    }
    banner.style.display = 'flex';
  } else {
    if (banner) {
      banner.style.display = 'none';
    }
  }
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setVitalState(cardId, statusId, valEl, critical, warning, isIdle = false) {
  const card   = document.getElementById(cardId);
  const status = document.getElementById(statusId);
  if (!card || !status) return;

  if (isIdle) {
    card.className = 'vital-card vc-idle';
    status.className = 'vital-status-dot vs-idle';
    status.textContent = 'STANDBY';
    if (valEl) valEl.style.color = 'var(--warn)';
  } else if (critical) {
    card.className = 'vital-card vc-crit';
    status.className = 'vital-status-dot vs-crit';
    status.textContent = 'CRIT';
    if (valEl) valEl.style.color = 'var(--critical)';
  } else if (warning) {
    card.className = 'vital-card vc-warn';
    status.className = 'vital-status-dot vs-warn';
    status.textContent = 'WARN';
    if (valEl) valEl.style.color = 'var(--warn)';
  } else {
    card.className = 'vital-card vc-ok';
    status.className = 'vital-status-dot vs-ok';
    status.textContent = 'OK';
    if (valEl) valEl.style.color = 'var(--text-1)';
  }
}

function updateSparkChart(chartKey, value) {
  const ch = CHARTS[chartKey];
  if (!ch) return;
  ch.data.datasets[0].data.push(value);
  ch.data.datasets[0].data.shift();
  ch.update('none');
}

function updateVitals(hr, spo2, temp, sys, dia, score, isFingerOn = true) {
  const hrEl   = document.getElementById('hr-val');
  const spo2El = document.getElementById('spo2-val');
  const tempEl = document.getElementById('temp-val');
  const bpEl   = document.getElementById('bp-val');

  if (!isFingerOn || hr <= 0) {
    // ─── STANDBY / NO FINGER STATE ───
    setText('hr-val', '--');
    setText('spo2-val', '--');
    setText('temp-val', (temp && temp > 0) ? temp.toFixed(1) : '--');
    setText('bp-val', '--/--');
    setText('ecg-meta', 'Standby · Place finger on MAX30102 sensor');
    if (document.getElementById('ecg-meta2'))
      setText('ecg-meta2', 'Awaiting Finger Contact');

    setText('hr-trend', 'STANDBY');
    setText('spo2-trend', 'STANDBY');
    if (document.getElementById('temp-trend'))
      setText('temp-trend', '↔ STABLE');

    // Mark cards as STANDBY (neutral amber/wire border, NOT red CRIT!)
    setVitalState('vc-hr',   'hr-status',   hrEl,   false, false, true);
    setVitalState('vc-spo2', 'spo2-status', spo2El, false, false, true);
    
    // Temperature: room temp (<34°C) is ambient room temperature, NOT hypothermia CRIT!
    const isAmbient = temp < 34.0;
    setVitalState('vc-temp', 'temp-status', tempEl, !isAmbient && (temp > 39.8 || temp < 35.0), !isAmbient && (temp > 38.0 || temp < 35.8), isAmbient);

    // Patient Advisor in clear layman terms
    updatePatientAdvisor('--', '--', (temp && temp > 0) ? temp.toFixed(1) : '--', '--', '--', 0, false);

    // EHR fields
    setText('ehr-hr',   '-- BPM');
    setText('ehr-spo2', '-- %');
    setText('ehr-temp', (temp && temp > 0) ? temp.toFixed(1) + ' °C' : '-- °C');
    setText('ehr-risk', '0 (STANDBY)');
    setText('ehr-time', new Date().toLocaleTimeString());

    // Quick Response summary strip
    setText('qr-hr',   '--');
    setText('qr-spo2', '--');
    setText('qr-temp', (temp && temp > 0) ? temp.toFixed(1) : '--');
    setText('qr-risk', '0');
    return;
  }

  // ─── ACTIVE MEASUREMENT STATE (Finger is on sensor) ───
  setText('hr-val', hr);
  setText('spo2-val', spo2);
  setText('temp-val', temp.toFixed(1));
  setText('bp-val', (sys || 120) + '/' + (dia || 80));
  setText('ecg-meta', hr + ' BPM · Lead II · ' + (hr > 100 ? 'Tachycardia' : hr < 55 ? 'Bradycardia' : 'Normal Sinus'));
  if (document.getElementById('ecg-meta2'))
    setText('ecg-meta2', hr + ' BPM · ' + (hr > 100 ? 'Tachycardia' : hr < 55 ? 'Bradycardia' : 'NSR'));

  // Status indicators based on actual patient vitals
  setVitalState('vc-hr',   'hr-status',   hrEl,   hr < 45 || hr > 120, hr > 100 || hr < 55, false);
  setVitalState('vc-spo2', 'spo2-status', spo2El, spo2 < 88, spo2 < 95, false);
  const isAmbient = temp < 34.0;
  setVitalState('vc-temp', 'temp-status', tempEl, !isAmbient && (temp > 39.8 || temp < 35.0), !isAmbient && (temp > 38.0 || temp < 35.8), isAmbient);

  // Trends
  if (STATE.hrHistory.length > 3) {
    const d = hr - STATE.hrHistory[STATE.hrHistory.length - 3];
    setText('hr-trend', d > 1 ? '↑ RISING' : d < -1 ? '↓ FALLING' : '↔ STABLE');
  }

  // Sparks
  updateSparkChart('sHr',   hr);
  updateSparkChart('sSpo2', spo2);
  updateSparkChart('sTemp', temp);
  updateSparkChart('sBp',   sys || 120);

  // EHR fields
  setText('ehr-hr',   hr + ' BPM');
  setText('ehr-spo2', spo2 + ' %');
  setText('ehr-temp', temp.toFixed(1) + ' °C');
  setText('ehr-risk', score);
  setText('ehr-time', new Date().toLocaleTimeString());

  // Quick Response summary strip fields
  setText('qr-hr',   hr);
  setText('qr-spo2', spo2);
  setText('qr-temp', temp.toFixed(1));
  setText('qr-risk', score);

  updatePatientAdvisor(hr, spo2, temp, sys || 120, dia || 80, score, true);
}

function updatePatientAdvisor(hr, spo2, temp, sys, dia, score, isFingerOn = true) {
  const pHrVal = document.getElementById('p-hr-val');
  if (!pHrVal) return;

  if (!isFingerOn) {
    setText('p-hr-val', '--');
    setText('p-spo2-val', '--');
    setText('p-temp-val', (typeof temp === 'number' ? temp.toFixed(1) : temp) + ' °C');
    setText('p-bp-val', '-- / --');
    setText('p-hr-desc', '🟡 Sensor Standby — Awaiting Finger');
    setText('p-spo2-desc', '🟡 Optical sensor waiting for contact');
    setText('p-temp-desc', parseFloat(temp) < 34 ? '⚪ Ambient Temperature Sensor' : '🟢 Body Temperature Active');
    setText('p-bp-desc', '⚪ Automatic Estimation Inactive');

    const mainMsg = document.getElementById('patient-main-msg');
    const chip = document.getElementById('patient-status-chip');
    if (chip) { chip.className = 'chip chip-a'; chip.textContent = '🟡 SENSOR STANDBY'; }
    if (mainMsg) {
      mainMsg.style.borderLeftColor = 'var(--warn)';
      mainMsg.innerHTML = `<strong>💡 Hardware Connected:</strong> Your ESP32 device is streaming live telemetry. Place your finger flat on the MAX30102 optical sensor LED to measure your heart rate and SpO₂ saturation.`;
    }
    return;
  }

  setText('p-hr-val', hr + ' BPM');
  setText('p-spo2-val', spo2 + '%');
  setText('p-temp-val', typeof temp === 'number' ? temp.toFixed(1) + ' °C' : temp + ' °C');
  setText('p-bp-val', sys + ' / ' + dia);

  // Heart Rate
  let hrDesc = '🟢 Healthy & Normal';
  if (hr > 100) hrDesc = '🔴 Fast Heartbeat (Tachycardia)';
  else if (hr < 55) hrDesc = '🟡 Slow Heartbeat (Bradycardia)';
  setText('p-hr-desc', hrDesc);

  // Oxygen
  let spo2Desc = '🟢 Excellent Blood Oxygen';
  if (spo2 < 92) spo2Desc = '🔴 Low Oxygen (Hypoxia) — Deep breath!';
  else if (spo2 < 95) spo2Desc = '🟡 Slightly Low Oxygen';
  setText('p-spo2-desc', spo2Desc);

  // Temp
  let tempDesc = '🟢 Normal Body Temperature';
  if (temp > 38.0) tempDesc = '🔴 Fever Detected';
  else if (temp < 35.5) tempDesc = '🟡 Low Body Temp (Hypothermia)';
  setText('p-temp-desc', tempDesc);

  // BP
  let bpDesc = '🟢 Ideal Pressure';
  if (sys > 140 || dia > 90) bpDesc = '🔴 High Blood Pressure (Hypertension)';
  else if (sys < 90) bpDesc = '🟡 Low Blood Pressure';
  setText('p-bp-desc', bpDesc);

  // Overall Main Summary Message in Plain English
  const mainMsg = document.getElementById('patient-main-msg');
  const chip = document.getElementById('patient-status-chip');
  if (!mainMsg) return;

  const tNum = typeof temp === 'number' ? temp : parseFloat(temp) || 36.6;

  if (score > 60 || hr > 115 || spo2 < 90 || tNum > 38.5) {
    if (chip) { chip.className = 'chip chip-r'; chip.textContent = '🔴 ATTENTION REQUIRED'; }
    mainMsg.style.borderLeftColor = 'var(--critical)';
    let reason = [];
    if (hr > 100) reason.push('fast heartbeat (' + hr + ' BPM)');
    if (spo2 < 95) reason.push('low oxygen (' + spo2 + '%)');
    if (tNum > 38.0) reason.push('fever (' + tNum.toFixed(1) + '°C)');
    if (sys > 140) reason.push('high blood pressure (' + sys + '/' + dia + ')');
    
    mainMsg.innerHTML = `<strong>⚠️ Attention Needed:</strong> Your sensors show ${reason.join(' and ')}. This suggests possible cardiac or respiratory strain. <strong>What to do:</strong> Sit down comfortably, drink water, and take deep breaths. If you feel chest pain or dizziness, contact a doctor immediately.`;
  } else if (score > 30 || hr > 100 || spo2 < 95 || tNum > 37.5) {
    if (chip) { chip.className = 'chip chip-a'; chip.textContent = '🟡 SLIGHT DEVIATION'; }
    mainMsg.style.borderLeftColor = 'var(--warn)';
    mainMsg.innerHTML = `<strong>🟡 Moderate Risk:</strong> One of your sensor values is slightly outside the resting baseline (Heart rate ${hr} BPM, Oxygen ${spo2}%). <strong>What to do:</strong> Rest for 5-10 minutes and avoid heavy exertion or caffeine.`;
  } else {
    if (chip) { chip.className = 'chip chip-g'; chip.textContent = '🟢 ALL VITALS HEALTHY'; }
    mainMsg.style.borderLeftColor = 'var(--pulse)';
    mainMsg.innerHTML = `<strong>🟢 Everything looks great!</strong> Your heart rate (${hr} BPM), oxygen level (${spo2}%), and body temperature are all in normal, healthy ranges. No cardiac condition detected.`;
  }
}

function renderRiskBreakdown(breakdown, recommendation) {
  const codeBlock = document.querySelector('#view-ai .code-block');
  if (!codeBlock) return;
  
  if (!breakdown) {
    return; // Don't override if no live AI data is present
  }
  
  const getProgressColor = (score) => {
    return score > 60 ? '#ff3e3e' : score > 30 ? '#ffaa00' : '#00ff88';
  };
  
  const items = [
    { label: 'Cardiac Arrhythmia', key: 'arrhythmia' },
    { label: 'Bradycardia', key: 'bradycardia' },
    { label: 'Tachycardia', key: 'tachycardia' },
    { label: 'Hypoxemia / Hypoxia', key: 'hypoxemia' },
    { label: 'Fever / Sepsis / Infection', key: 'fever_infection' },
    { label: 'Cardiovascular Stress', key: 'cardiovascular_stress' }
  ];
  
  let html = `<div style="display:flex;flex-direction:column;gap:9px;padding:4px">`;
  
  items.forEach(it => {
    const itemData = breakdown[it.key];
    const score = itemData ? itemData.score : 0.0;
    const explanation = itemData ? itemData.explanation : 'No data';
    const color = getProgressColor(score);
    
    html += `
      <div>
        <div style="display:flex;justify-content:space-between;font-size:10px;margin-bottom:2px">
          <span style="font-family:var(--sans);font-weight:700;color:var(--text-1)">${it.label}</span>
          <span style="font-family:var(--mono);color:${color};margin-left:auto;font-weight:700">${score}%</span>
        </div>
        <div style="height:5px;background:var(--deep);border-radius:2px;overflow:hidden;margin-bottom:3px">
          <div style="height:100%;width:${score}%;background:${color};border-radius:2px"></div>
        </div>
        <div style="font-size:8px;color:var(--text-3);line-height:1.2">${explanation}</div>
      </div>
    `;
  });
  
  if (recommendation) {
    html += `
      <div style="margin-top:8px;padding:8px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05);border-radius:var(--r)">
        <div style="font-size:9px;font-family:var(--mono);color:var(--cyan);margin-bottom:2px">CLINICAL ACTION PATHWAY</div>
        <div style="font-size:10px;font-weight:700;color:${recommendation.color === 'red' ? 'var(--critical)' : recommendation.color === 'amber' ? 'var(--warn)' : 'var(--pulse)'};margin-bottom:3px">${recommendation.action}</div>
        <div style="font-size:9px;color:var(--text-2);line-height:1.3">${recommendation.reasoning}</div>
      </div>
    `;
  }
  
  html += `</div>`;
  codeBlock.style.fontFamily = 'var(--sans)';
  codeBlock.style.fontSize = '11px';
  codeBlock.style.whiteSpace = 'normal';
  codeBlock.style.padding = '8px 12px';
  codeBlock.innerHTML = html;
}

function renderEcgAiInterpretation(probs) {
  const interp = document.getElementById('ecg-ai-interp');
  if (!interp) return;
  
  const classes = [
    { name: 'Normal', val: probs[0] !== undefined ? probs[0] : 0, color: 'var(--pulse)' },
    { name: 'Premature Ventricular Contraction (PVC)', val: probs[1] !== undefined ? probs[1] : 0, color: 'var(--warn)' },
    { name: 'Premature Atrial Contraction (PAC)', val: probs[2] !== undefined ? probs[2] : 0, color: 'var(--cyan)' },
    { name: 'Atrial Fibrillation (AFib)', val: probs[3] !== undefined ? probs[3] : 0, color: 'var(--critical)' },
    { name: 'Bradycardia', val: probs[4] !== undefined ? probs[4] : 0, color: '#0077a8' },
    { name: 'Tachycardia', val: probs[5] !== undefined ? probs[5] : 0, color: '#fbbf24' },
    { name: 'Heart Block', val: probs[6] !== undefined ? probs[6] : 0, color: '#a78bfa' },
    { name: 'Bundle Branch Block (BBB)', val: probs[7] !== undefined ? probs[7] : 0, color: '#67e8f9' },
    { name: 'Myocardial Ischemia', val: probs[8] !== undefined ? probs[8] : 0, color: '#fca5a5' },
    { name: 'Myocardial Infarction', val: probs[9] !== undefined ? probs[9] : 0, color: 'var(--critical)' }
  ];
  
  const sorted = [...classes].sort((a, b) => b.val - a.val);
  
  let html = sorted.map(c => `
    <div style="margin-bottom:6px">
      <div style="display:flex;justify-content:space-between;font-size:10px;margin-bottom:2px">
        <span style="font-family:var(--sans);color:var(--text-2)">${c.name}</span>
        <span style="font-family:var(--mono);color:${c.color};margin-left:auto">${(c.val * 100).toFixed(1)}%</span>
      </div>
      <div style="height:4px;background:var(--deep);border-radius:2px;overflow:hidden">
        <div style="height:100%;width:${c.val * 100}%;background:${c.color};border-radius:2px"></div>
      </div>
    </div>
  `).join('');
  
  interp.innerHTML = html;
}

function renderExplainability(explainability, ecg_probabilities) {
  // Fallback mock values for smooth demo UI rendering
  if (!explainability) {
    explainability = {
      gradcam: Array.from({ length: 90 }, (_, i) => Math.min(1.0, Math.max(0.05, Math.sin(i / 6.0)**2 * 0.85 + (Math.random() - 0.5) * 0.1))),
      vitals_saliency: [0.12, 0.03, 0.38, 0.22, 0.08, 0.06, 0.04, 0.04, 0.03],
      vitals_names: ["Age", "Gender", "HR", "SpO2", "Temp", "BP Sys", "BP Dia", "Resp Rate", "Symptoms"]
    };
  }

  // 1. Grad-CAM Activation Heatmap Strip
  const gradcamBar = document.getElementById('gradcam-bar');
  const gradcamPeak = document.getElementById('gradcam-peak');
  
  if (gradcamBar && explainability && explainability.gradcam) {
    const gc = explainability.gradcam;
    const maxGc = Math.max(...gc);
    const peakIdx = gc.indexOf(maxGc);
    
    const html = gc.map(val => {
      const hue = Math.round((1 - val) * 130); // 130 (green) → 0 (red)
      const color = `hsl(${hue}, 100%, 48%)`;
      return `<div style="flex:1;height:100%;background:${color};opacity:${0.4 + val * 0.6}"></div>`;
    }).join('');
    
    gradcamBar.innerHTML = html;
    if (gradcamPeak) {
      gradcamPeak.textContent = `Peak Focus: sample #${peakIdx} (${(maxGc * 100).toFixed(0)}%)`;
    }
  }

  // 2. Vitals Gradient Saliency Progress Bars
  const vitalsBars = document.getElementById('vitals-saliency-bars');
  if (vitalsBars && explainability && explainability.vitals_saliency) {
    const names = explainability.vitals_names || ["Age", "Gender", "HR", "SpO2", "Temp", "BP Sys", "BP Dia", "Resp Rate", "Symptoms"];
    const saliency = explainability.vitals_saliency;
    
    const combined = names.map((n, i) => ({ name: n, val: saliency[i] || 0 })).sort((a, b) => b.val - a.val);
    
    vitalsBars.innerHTML = combined.map(v => {
      const pct = (v.val * 100).toFixed(1);
      const color = v.val > 0.25 ? 'var(--critical)' : v.val > 0.10 ? 'var(--warn)' : 'var(--pulse)';
      return `
        <div>
          <div style="display:flex;justify-content:space-between;font-size:9px;margin-bottom:1px;font-family:var(--mono)">
            <span style="color:var(--text-1)">${v.name}</span>
            <span style="color:${color};font-weight:700">${pct}%</span>
          </div>
          <div style="height:5px;background:var(--deep);border-radius:2px;overflow:hidden">
            <div style="height:100%;width:${pct}%;background:${color};border-radius:2px"></div>
          </div>
        </div>
      `;
    }).join('');
  }

  // 3. Pathology Probabilities
  const classBars = document.getElementById('class-prob-bars');
  if (ecg_probabilities) {
    renderEcgAiInterpretation(ecg_probabilities);
    if (classBars) {
      classBars.innerHTML = document.getElementById('ecg-ai-interp') ? document.getElementById('ecg-ai-interp').innerHTML : '';
    }
  }
}

function updateRisk(score, ecg_probabilities, risk_breakdown, recommendation) {
  const level = recommendation ? recommendation.level : getRiskLevel(score);
  const colors = { LOW: 'var(--pulse)', MEDIUM: 'var(--warn)', MODERATE: 'var(--warn)', HIGH: 'var(--critical)', EMERGENCY: 'var(--critical)' };
  const arcColors = { LOW: '#00ff88', MEDIUM: '#ffaa00', MODERATE: '#ffaa00', HIGH: '#ff3e3e', EMERGENCY: '#ff3e3e' };
  const emojis  = { LOW: '▲', MEDIUM: '▲', MODERATE: '▲', HIGH: '▲', EMERGENCY: '▲' };

  // Topbar chip
  const chip = document.getElementById('risk-chip');
  if (chip) {
    let lKey = (level || 'LOW').toUpperCase().replace(/_|\s+RISK/g, '').trim();
    if (!['LOW', 'MEDIUM', 'MODERATE', 'HIGH', 'EMERGENCY'].includes(lKey)) {
      lKey = getRiskLevel(score);
    }
    const icons = { LOW: '🟢', MEDIUM: '🟡', MODERATE: '🟡', HIGH: '🔴', EMERGENCY: '🚨' };
    const icon = icons[lKey] || '🟢';
    chip.className = 'risk-chip rc-' + (lKey === 'MODERATE' ? 'medium' : lKey.toLowerCase());
    chip.textContent = `${icon} ${lKey} RISK`;
  }

  // Gauge
  setText('g-score', score);
  const gNum = document.getElementById('g-score');
  const lKey = (level || 'LOW').toUpperCase();
  if (gNum) gNum.style.color = arcColors[lKey] || '#00ff88';

  const arc = document.getElementById('g-arc');
  if (arc) {
    arc.style.stroke = arcColors[lKey] || '#00ff88';
    arc.style.strokeDashoffset = 201 * (1 - score / 100);
  }

  // Level badge
  const badge = document.getElementById('risk-level-badge');
  if (badge) {
    badge.className = 'chip chip-' + (lKey === 'LOW' ? 'g' : (lKey === 'MEDIUM' || lKey === 'MODERATE') ? 'a' : 'r');
    badge.style.textAlign = 'center';
    badge.style.padding = '5px';
    badge.style.borderRadius = 'var(--r)';
    badge.style.marginBottom = '8px';
    badge.style.fontSize = '10px';
    badge.textContent = '● ' + lKey + ' RISK';
  }

  // Prediction
  const p = document.getElementById('predict-text');
  if (p) {
    if (recommendation) {
      p.textContent = recommendation.reasoning;
    } else {
      p.textContent = getPrediction(score, STATE.hrHistory.slice(-1)[0] || 72, STATE.spo2History.slice(-1)[0] || 98);
    }
  }

  // EHR risk chip
  const erc = document.getElementById('ehr-risk-chip');
  if (erc) {
    erc.className = 'chip chip-' + (lKey === 'LOW' ? 'g' : (lKey === 'MEDIUM' || lKey === 'MODERATE') ? 'a' : 'r');
    erc.textContent = lKey;
  }
  
  if (ecg_probabilities) {
    renderEcgAiInterpretation(ecg_probabilities);
  }
  if (risk_breakdown) {
    renderRiskBreakdown(risk_breakdown, recommendation);
  }
}

function updateCDSS(hr, spo2, temp, score, recommendation, isFingerOn = true) {
  let items;
  if (!isFingerOn || hr <= 0) {
    items = getCDSS(0, 0, temp, 0, false);
  } else if (recommendation) {
    items = [
      { type: 'alert', msg: recommendation.action },
      { type: 'info', msg: recommendation.reasoning }
    ];
  } else {
    items = getCDSS(hr, spo2, temp, score, true);
  }
  const typeClass = { warn: 'cdss-warn', info: 'cdss-info', alert: 'cdss-alert' };

  const html = items.map(i => `<div class="cdss-item ${typeClass[i.type]}">${i.msg}</div>`).join('');

  const full = document.getElementById('cdss-full');
  if (full) full.innerHTML = html;
  const mini = document.getElementById('cdss-mini');
  if (mini) mini.innerHTML = items.slice(0, 2).map(i => `<div class="cdss-item ${typeClass[i.type]}" style="font-size:9px;padding:4px 6px">${i.msg}</div>`).join('');
  const cnt = document.getElementById('cdss-cnt');
  if (cnt) cnt.textContent = items.length + ' INSIGHT' + (items.length !== 1 ? 'S' : '');
}

function updateEHR(hr, spo2, temp, score, recommendation) {
  const entry = {
    time: new Date().toLocaleTimeString(),
    hr, spo2,
    temp: temp.toFixed(1),
    score,
    pred: recommendation ? recommendation.reasoning.substring(0, 50) + '...' : getPrediction(score, hr, spo2).replace(/[🔮⚠️🚨⚡📈✅🧠💊ℹ️]/g, '').trim().substring(0, 50) + '...'
  };
  STATE.ehrLog.unshift(entry);
  if (STATE.ehrLog.length > 20) STATE.ehrLog.pop();

  const tbody = document.getElementById('ehr-tbody');
  if (!tbody) return;
  const scoreColor = s => s > 60 ? 'var(--critical)' : s > 30 ? 'var(--warn)' : 'var(--pulse)';
  tbody.innerHTML = STATE.ehrLog.map(e =>
    `<tr>
      <td>${e.time}</td>
      <td>${e.hr}</td>
      <td>${e.spo2}</td>
      <td>${e.temp}</td>
      <td style="color:${scoreColor(e.score)}">${e.score}</td>
      <td style="font-family:var(--sans);font-size:9px;color:var(--text-3);max-width:180px">${e.pred}</td>
    </tr>`
  ).join('');
}

// ═══════════════════════════════════════════════════════
//  ECG VIEW
// ═══════════════════════════════════════════════════════
function renderEcgInterp() {
  const interp = document.getElementById('ecg-ai-interp');
  if (!interp) return;
  const items = [
    { t: 'info',  m: '✅ Normal sinus rhythm detected (NSR)' },
    { t: 'info',  m: '✅ No ST elevation/depression observed' },
    { t: 'info',  m: '✅ QRS morphology within normal range' },
    { t: 'info',  m: '📐 PR interval: 142ms (normal 120–200ms)' }
  ];
  interp.innerHTML = items.map(i =>
    `<div class="cdss-item cdss-${i.t === 'info' ? 'info' : 'warn'}" style="font-size:10px">${i.m}</div>`
  ).join('');
}

// ═══════════════════════════════════════════════════════
//  EMERGENCY
// ═══════════════════════════════════════════════════════
function triggerEmergency() {
  if (STATE.emgDismissed) return;
  if (!STATE.isHardwareOnline && !STATE.demoSimMode) return;
  STATE.emgShown = true;
  const overlay = document.getElementById('emg-overlay');
  if (overlay) {
    overlay.style.setProperty('display', 'flex', 'important');
    overlay.classList.add('show');
  }
  // Beep alert
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    for (let i = 0; i < 3; i++) {
      const o = ac.createOscillator(), g = ac.createGain();
      o.type = 'square'; o.frequency.value = 880;
      g.gain.value = 0.07;
      o.connect(g); g.connect(ac.destination);
      o.start(ac.currentTime + i * 0.55);
      o.stop(ac.currentTime + i * 0.55 + 0.2);
    }
  } catch (e) {}
  try { notify('🚨 HIGH RISK ALERT! Emergency protocol activated.', 'error'); } catch(e) {}

  // Add to alerts
  const alertEl = {
    type: 'alert',
    time: new Date().toLocaleTimeString(),
    msg: 'HIGH RISK detected. Risk score: ' + (STATE.riskScore || 'HIGH') + '. Emergency overlay triggered.'
  };
  STATE.alerts.unshift(alertEl);
  try { renderAlerts(); } catch (e) {}
  const ab = document.getElementById('alert-badge');
  if (ab) ab.textContent = STATE.alerts.length;
}

function closeEmg() {
  STATE.emgDismissed = true;
  STATE.emgShown = true;
  const overlay = document.getElementById('emg-overlay');
  if (overlay) {
    overlay.classList.remove('show');
    overlay.style.setProperty('display', 'none', 'important');
  }
  try {
    notify('✅ Emergency alert acknowledged by ' + (STATE.user || 'Physician'), 'warning');
  } catch (e) {}
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeEmg();
  }
});

// ═══════════════════════════════════════════════════════
//  APPOINTMENTS
// ═══════════════════════════════════════════════════════
function calcPri() {
  const age = parseInt(document.getElementById('a-age').value) || 0;
  const sv  = parseInt(document.getElementById('a-sym').value) || 1;
  const af  = age > 65 ? 3 : age > 50 ? 2 : age > 30 ? 1 : 0;
  const s   = Math.min(100, Math.round(sv * 10 + af * 5 + STATE.riskScore * 0.08));
  setText('pri-score', s || '—');
  const hint = document.getElementById('pri-hint');
  if (!hint) return;
  if (s > 70) {
    hint.style.color = 'var(--critical)';
    hint.textContent = '⚡ HIGH PRIORITY — Immediate slot: Today ' + (new Date().getHours() + 1) + ':00';
  } else if (s > 40) {
    hint.style.color = 'var(--warn)';
    hint.textContent = '⚠️ MEDIUM PRIORITY — Next available: Tomorrow 09:00';
  } else {
    hint.style.color = 'var(--text-3)';
    hint.textContent = '📅 NORMAL — Slot matches preferred date.';
  }
}

function bookAppt() {
  const name = document.getElementById('a-name').value.trim();
  if (!name) { notify('⚠️ Enter patient name', 'warning'); return; }
  const age  = document.getElementById('a-age').value || '—';
  const sv   = parseInt(document.getElementById('a-sym').value) || 1;
  const stxt = document.getElementById('a-sym').options[document.getElementById('a-sym').selectedIndex].text;
  const af   = parseInt(age) > 65 ? 3 : parseInt(age) > 50 ? 2 : 1;
  const s    = Math.min(100, Math.round(sv * 10 + af * 5 + STATE.riskScore * 0.08));
  const clr  = s > 70 ? '#ff3e3e' : s > 40 ? '#ffaa00' : '#3b82f6';
  const time = document.getElementById('a-time').value;

  STATE.appointments.unshift({ name, age, symptom: stxt, time, score: s, color: clr });
  renderApptQueue();
  renderApptPreview();

  const cnt = document.getElementById('q-cnt');
  if (cnt) cnt.textContent = STATE.appointments.length + ' PENDING';
  const badge = document.getElementById('appt-badge');
  if (badge) badge.textContent = STATE.appointments.length;

  notify('📅 Appointment booked: ' + name + ' (Score ' + s + ')', 'success');
  document.getElementById('a-name').value = '';
  document.getElementById('a-age').value  = '';
  setText('pri-score', '—');
  if (document.getElementById('pri-hint')) document.getElementById('pri-hint').textContent = '';
}

function renderApptQueue() {
  const el = document.getElementById('appt-queue-list');
  if (!el) return;
  const sorted = [...STATE.appointments].sort((a, b) => b.score - a.score);
  el.innerHTML = sorted.map(a => `
    <div class="appt-item">
      <div class="appt-bar" style="background:${a.color}"></div>
      <div>
        <div class="appt-name">${a.name}, ${a.age}</div>
        <div class="appt-detail">${a.symptom} · ${a.time}</div>
      </div>
      <div class="appt-score" style="color:${a.color}">${a.score}</div>
    </div>`
  ).join('');
}

function renderApptPreview() {
  const el = document.getElementById('appt-preview');
  if (!el) return;
  const sorted = [...STATE.appointments].sort((a, b) => b.score - a.score).slice(0, 3);
  el.innerHTML = sorted.map(a => `
    <div class="appt-item">
      <div class="appt-bar" style="background:${a.color}"></div>
      <div>
        <div class="appt-name">${a.name}</div>
        <div class="appt-detail">${a.symptom} · ${a.time} · ${a.score}</div>
      </div>
    </div>`
  ).join('');
}

// ═══════════════════════════════════════════════════════
//  ALERTS
// ═══════════════════════════════════════════════════════
function renderAlerts() {
  const el = document.getElementById('alert-list');
  if (!el) return;
  const defaultAlerts = [
    { type: 'warn',  time: 'Yesterday · 14:28', msg: '<strong>SpO₂ Alert</strong> — SpO₂ dropped to 93%. O₂ support administered. Resolved in 4 min.' },
    { type: 'alert', time: '2 days ago · 10:15', msg: '<strong>Tachycardia Episode</strong> — HR 118 BPM × 8 min. TinyML LSTM flagged abnormal. Physician reviewed.' },
    { type: 'info',  time: 'Today · 09:00', msg: '<strong>Appointment Reminder</strong> — Ravi Kumar (Chest Pain) — URGENT — 10:30 today. Priority Score: 87.' }
  ];
  const all = [...STATE.alerts.map(a => ({ type: a.type, time: a.time, msg: a.msg })), ...defaultAlerts];
  const typeClass = { warn: 'cdss-warn', info: 'cdss-info', alert: 'cdss-alert' };
  el.innerHTML = all.map(a => `
    <div class="cdss-item ${typeClass[a.type]}" style="font-size:11px;padding:9px">
      <div>
        <div style="font-family:var(--mono);font-size:8px;color:inherit;opacity:.6;margin-bottom:2px">${a.time}</div>
        ${a.msg}
      </div>
    </div>`
  ).join('');
}

function clearAlerts() {
  STATE.alerts = [];
  renderAlerts();
  document.getElementById('alert-badge').style.display = 'none';
  notify('🔔 All alerts cleared', 'success');
}

// ═══════════════════════════════════════════════════════
//  CONTROLS
// ═══════════════════════════════════════════════════════
function setSpd(s, el) {
  STATE.ecgSpeed = s;
  document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}
function setHRange(r, el) {
  STATE.histRange = r;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  buildHistChart();
}
function themeToggle() {
  STATE.theme = STATE.theme === 'dark' ? 'light' : 'dark';
  document.body.classList.toggle('light', STATE.theme === 'light');
  notify('Theme: ' + STATE.theme.toUpperCase(), 'info');
}

// ═══════════════════════════════════════════════════════
//  TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════
const TOAST_ICONS = { success: '✅', warning: '⚠️', error: '🔴', info: 'ℹ️' };
function notify(msg, type = 'info') {
  const dock = document.getElementById('toast-dock');
  const el   = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = `<span class="toast-icon">${TOAST_ICONS[type] || 'ℹ️'}</span><span>${msg}</span>`;
  dock.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 200); }, 3500);
}

// ═══════════════════════════════════════════════════════
//  AUTO-INIT ON PAGE LOAD
// ═══════════════════════════════════════════════════════
function bootPulseTech() {
  const token = localStorage.getItem('pulsetech_token');
  if (token) {
    const loginScr = document.getElementById('login-screen');
    if (loginScr) {
      loginScr.style.setProperty('display', 'none', 'important');
      try { loginScr.remove(); } catch(e) {}
    }
    const savedUser = localStorage.getItem('pulsetech_user');
    if (savedUser) {
      try {
        const u = JSON.parse(savedUser);
        STATE.role = u.role || 'doctor';
        STATE.user = u.name || 'Dr. Arpit';
        const uNameEl = document.getElementById('u-name');
        if (uNameEl) uNameEl.textContent = STATE.user;
        const uRoleEl = document.getElementById('u-role');
        if (uRoleEl) uRoleEl.textContent = STATE.role.toUpperCase();
        const avMap = { doctor: 'DA', patient: 'PA', admin: 'SA' };
        const uAvEl = document.getElementById('u-avatar');
        if (uAvEl) uAvEl.textContent = avMap[STATE.role] || 'DA';
      } catch(e) {}
    }
  }
  try { initAllCharts(); } catch(e) { console.warn('[Chart] bootPulseTech error:', e); }
  try { startDataStream(); } catch(e) { console.warn('[Data] bootPulseTech error:', e); }
  try { renderApptQueue(); } catch(e) {}
  try { renderAlerts(); } catch(e) {}
  try { renderApptPreview(); } catch(e) {}
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const scr = document.getElementById('login-screen');
    if (scr && scr.style.display !== 'none' && document.body.contains(scr)) {
      doLogin();
    }
  }
});

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', bootPulseTech);
} else {
  bootPulseTech();
}

// ═══════════════════════════════════════════════════════
//  VOICE ASSISTANT (simulated)
// ═══════════════════════════════════════════════════════
function toggleVoice() {
  STATE.voiceOn = !STATE.voiceOn;
  const btn = document.getElementById('voice-fab');
  btn.classList.toggle('listening', STATE.voiceOn);
  if (STATE.voiceOn) {
    notify('🎤 Voice assistant active — listening...', 'info');
    const responses = [
      'Patient risk level is currently ' + STATE.riskLevel + '.',
      'Heart rate: ' + (STATE.hrHistory.slice(-1)[0] || '--') + ' BPM — ' + STATE.riskLevel + '.',
      'SpO₂: ' + (STATE.spo2History.slice(-1)[0] || '--') + '%. All within normal range.',
      'TinyML risk score: ' + STATE.riskScore + ' out of 100.',
      'Navigating to ECG live view...',
      'Loading appointment queue... ' + STATE.appointments.length + ' patients pending.'
    ];
    setTimeout(() => {
      notify('🤖 ' + responses[Math.floor(Math.random() * responses.length)], 'success');
      STATE.voiceOn = false;
      btn.classList.remove('listening');
    }, 2000);
  }
}

// ═══════════════════════════════════════════════════════
//  PDF REPORT
// ═══════════════════════════════════════════════════════
function dlReport() {
  notify('📄 Generating patient report...', 'info');
  setTimeout(() => notify('⬇ Report: PulseTech_PT-2024-0381_' + new Date().toLocaleDateString().replace(/\//g, '-') + '.pdf', 'success'), 1800);
}

// ═══════════════════════════════════════════════════════
//  CLOCK
// ═══════════════════════════════════════════════════════
setInterval(() => {
  const el = document.getElementById('clock-display');
  if (el) el.textContent = new Date().toLocaleTimeString('en-IN', { hour12: false });
}, 1000);

// ═══════════════════════════════════════════════════════
//  UTILITY
// ═══════════════════════════════════════════════════════
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// Ensure Blood Pressure card is removed from DOM even if HTML was cached
const bpCard = document.getElementById('vc-bp');
if (bpCard) bpCard.remove();
const vGrid = document.getElementById('vitals-grid');
if (vGrid) vGrid.style.gridTemplateColumns = 'repeat(3, 1fr)';

document.getElementById('a-date').value = new Date().toISOString().split('T')[0];
renderApptQueue();
renderAlerts();
renderApptPreview();
renderEcgAiInterpretation([0.98, 0.01, 0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00]);

// Auto-Unregister all ServiceWorkers to guarantee latest fresh code
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(regs => {
    for (const r of regs) r.unregister();
  }).catch(() => {});
}

// ═══════════════════════════════════════════════════════
//  WEBRTC WEBCALL TELEHEALTH & EMERGENCY FACILITY
// ═══════════════════════════════════════════════════════
let localStream = null;
let remoteStream = null;
let peerConnection = null;
let callTimerInterval = null;
let callStartTime = 0;
let isMicMuted = false;
let isCamOff = false;

const rtcConfig = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' }
  ]
};

async function startWebCall(peerName = 'Dr. Arpit (Attending Physician)', peerRole = 'DOCTOR') {
  const modal = document.getElementById('webcall-modal');
  if (modal) modal.style.display = 'flex';

  const nameEl = document.getElementById('call-peer-name');
  if (nameEl) nameEl.textContent = peerName;
  const avatarEl = document.getElementById('call-peer-avatar');
  if (avatarEl) avatarEl.textContent = peerName.split(' ').map(n=>n[0]).join('').slice(0, 2) || 'PT';
  const statusEl = document.getElementById('call-peer-status');
  if (statusEl) statusEl.textContent = 'Requesting camera & microphone access...';

  // Update live vitals overlay in call
  const hrVal = document.getElementById('hr-val') ? document.getElementById('hr-val').textContent : '75';
  const spo2Val = document.getElementById('spo2-val') ? document.getElementById('spo2-val').textContent : '98';
  const tempVal = document.getElementById('temp-val') ? document.getElementById('temp-val').textContent : '36.6';
  setText('call-v-hr', hrVal + ' BPM');
  setText('call-v-spo2', spo2Val + '%');
  setText('call-v-temp', tempVal + '°C');

  try {
    // 1. Get user media (mic + camera)
    localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    const localVideo = document.getElementById('local-video');
    if (localVideo) localVideo.srcObject = localStream;

    if (statusEl) statusEl.textContent = '● Connected · Encrypted WebRTC Telehealth Line';
    
    // 2. Initialize WebRTC peer connection
    initPeerConnection();

    // 3. Start call timer
    callStartTime = Date.now();
    if (callTimerInterval) clearInterval(callTimerInterval);
    callTimerInterval = setInterval(updateCallTimer, 1000);

    // 4. Send WebRTC Call Init signal over WebSocket
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'WEBRTC_CALL_INIT', peerName, peerRole }));
    }

    notify(`📞 WebCall initiated with ${peerName}`, 'success');

  } catch (err) {
    console.warn('[WebRTC] Camera/Mic access note:', err);
    if (statusEl) statusEl.textContent = 'Audio-Only Consultation Mode Active (Camera offline)';
    
    callStartTime = Date.now();
    if (callTimerInterval) clearInterval(callTimerInterval);
    callTimerInterval = setInterval(updateCallTimer, 1000);
    
    notify('🎤 Microphones active — Audio Consultation live', 'info');
  }
}

function initPeerConnection() {
  try {
    peerConnection = new RTCPeerConnection(rtcConfig);
    
    if (localStream) {
      localStream.getTracks().forEach(track => peerConnection.addTrack(track, localStream));
    }

    peerConnection.ontrack = (event) => {
      const remoteVideo = document.getElementById('remote-video');
      const placeholder = document.getElementById('remote-avatar-placeholder');
      if (remoteVideo && event.streams[0]) {
        remoteVideo.srcObject = event.streams[0];
        if (placeholder) placeholder.style.display = 'none';
      }
    };

    peerConnection.onicecandidate = (event) => {
      if (event.candidate && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'WEBRTC_CANDIDATE', candidate: event.candidate }));
      }
    };

  } catch (e) {
    console.error('[WebRTC] PeerConnection init error:', e);
  }
}

function updateCallTimer() {
  const elapsedSec = Math.floor((Date.now() - callStartTime) / 1000);
  const m = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
  const s = String(elapsedSec % 60).padStart(2, '0');
  setText('webcall-timer', `${m}:${s}`);
}

function toggleMuteMic() {
  if (!localStream) {
    isMicMuted = !isMicMuted;
    const btn = document.getElementById('btn-mute-mic');
    if (btn) {
      btn.style.background = isMicMuted ? 'var(--critical)' : 'rgba(255,255,255,.08)';
      btn.textContent = isMicMuted ? '🔇' : '🎤';
    }
    notify(isMicMuted ? '🔇 Microphone muted' : '🎤 Microphone unmuted', 'info');
    return;
  }
  const audioTrack = localStream.getAudioTracks()[0];
  if (audioTrack) {
    audioTrack.enabled = !audioTrack.enabled;
    isMicMuted = !audioTrack.enabled;
    const btn = document.getElementById('btn-mute-mic');
    if (btn) {
      btn.style.background = isMicMuted ? 'var(--critical)' : 'rgba(255,255,255,.08)';
      btn.textContent = isMicMuted ? '🔇' : '🎤';
    }
    notify(isMicMuted ? '🔇 Microphone muted' : '🎤 Microphone unmuted', 'info');
  }
}

function toggleCam() {
  if (!localStream) {
    isCamOff = !isCamOff;
    const btn = document.getElementById('btn-toggle-cam');
    if (btn) {
      btn.style.background = isCamOff ? 'var(--critical)' : 'rgba(255,255,255,.08)';
      btn.textContent = isCamOff ? '📷' : '📹';
    }
    notify(isCamOff ? '📷 Camera turned off' : '📹 Camera active', 'info');
    return;
  }
  const videoTrack = localStream.getVideoTracks()[0];
  if (videoTrack) {
    videoTrack.enabled = !videoTrack.enabled;
    isCamOff = !videoTrack.enabled;
    const btn = document.getElementById('btn-toggle-cam');
    if (btn) {
      btn.style.background = isCamOff ? 'var(--critical)' : 'rgba(255,255,255,.08)';
      btn.textContent = isCamOff ? '📷' : '📹';
    }
    notify(isCamOff ? '📷 Camera turned off' : '📹 Camera active', 'info');
  }
}

async function shareScreen() {
  try {
    const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    const screenTrack = screenStream.getVideoTracks()[0];
    if (peerConnection) {
      const sender = peerConnection.getSenders().find(s => s.track && s.track.kind === 'video');
      if (sender) sender.replaceTrack(screenTrack);
    }
    const localVideo = document.getElementById('local-video');
    if (localVideo) localVideo.srcObject = screenStream;
    notify('🖥️ Screen / Live ECG waveform shared in call', 'success');
  } catch (err) {
    console.warn('[WebRTC] Screen share cancelled:', err);
  }
}

function endWebCall() {
  if (callTimerInterval) clearInterval(callTimerInterval);
  if (localStream) {
    localStream.getTracks().forEach(t => t.stop());
    localStream = null;
  }
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'WEBRTC_CALL_END' }));
  }

  const modal = document.getElementById('webcall-modal');
  if (modal) modal.style.display = 'none';

  const placeholder = document.getElementById('remote-avatar-placeholder');
  if (placeholder) placeholder.style.display = 'flex';

  notify('📞 Consultation call ended', 'info');
}


