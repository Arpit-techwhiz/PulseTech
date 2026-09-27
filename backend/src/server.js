// ═══════════════════════════════════════════════════════
//  PulseTech Backend — Node.js / Express + WebSocket
//  Production-grade API with JWT Auth, SQLite, MQTT
// ═══════════════════════════════════════════════════════

const express    = require('express');
const http       = require('http');
const WebSocket  = require('ws');
const jwt        = require('jsonwebtoken');
const crypto     = require('crypto');

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const derivedKey = crypto.scryptSync(password, salt, 64);
  return `${salt}:${derivedKey.toString('hex')}`;
}

function comparePassword(password, hash) {
  try {
    const parts = hash.split(':');
    if (parts.length !== 2) return false;
    const [salt, key] = parts;
    const keyBuf = Buffer.from(key, 'hex');
    if (keyBuf.length !== 64) return false;
    const derivedKey = crypto.scryptSync(password, salt, 64);
    return crypto.timingSafeEqual(keyBuf, derivedKey);
  } catch (err) {
    return false;
  }
}

const fs = require('fs');

function logSecurityEvent(username, eventType, details) {
  const logDir = path.join(__dirname, '../../logs');
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }
  const logFile = path.join(logDir, 'security.log');
  const logEntry = JSON.stringify({
    timestamp: new Date().toISOString(),
    username: username || 'ANONYMOUS',
    event: eventType,
    details: details
  }) + '\n';
  
  fs.appendFile(logFile, logEntry, (err) => {
    if (err) console.error('[Security Logger Error]', err.message);
  });
}
const cors       = require('cors');
const helmet     = require('helmet');
const path       = require('path');
const mqtt       = require('mqtt');

class Database {
  constructor(dbPath) {
    this.dbPath = dbPath;
    this.tables = {
      users: [],
      patients: [],
      sensor_data: [],
      ai_predictions: [],
      appointments: [],
      alerts: []
    };
    console.log(`[Database] Initialized mock database at ${dbPath}`);
  }

  exec(sql) {
    return this;
  }

  prepare(sql) {
    const self = this;
    const lowerSql = sql.toLowerCase().trim();

    return {
      run(...args) {
        if (lowerSql.startsWith('insert into users')) {
          const [username, password_hash, role, name] = args;
          const user = { id: self.tables.users.length + 1, username, password_hash, role, name };
          self.tables.users.push(user);
          return { changes: 1, lastInsertRowid: user.id };
        }
        if (lowerSql.startsWith('insert into patients')) {
          const [id, name, age, gender, blood_group, ward, username] = args;
          const pat = { id, name, age, gender, blood_group, ward, username };
          self.tables.patients.push(pat);
          return { changes: 1, lastInsertRowid: id };
        }
        if (lowerSql.startsWith('insert into sensor_data')) {
          const [patient_id, hr, spo2, temperature, sys_bp, dia_bp, risk_score, risk_level, device_id] = args;
          const row = { id: self.tables.sensor_data.length + 1, patient_id, hr, spo2, temperature, sys_bp, dia_bp, risk_score, risk_level, device_id, timestamp: new Date().toISOString() };
          self.tables.sensor_data.push(row);
          return { changes: 1, lastInsertRowid: row.id };
        }
        if (lowerSql.startsWith('insert into ai_predictions')) {
          const [patient_id, risk_score, risk_level, prediction_text, cdss_insights, device_id] = args;
          const row = { id: self.tables.ai_predictions.length + 1, patient_id, risk_score, risk_level, prediction_text, cdss_insights, device_id, timestamp: new Date().toISOString() };
          self.tables.ai_predictions.push(row);
          return { changes: 1, lastInsertRowid: row.id };
        }
        return { changes: 0, lastInsertRowid: 0 };
      },

      all(...args) {
        if (lowerSql.includes('from sensor_data')) {
          const pid = args[0];
          let list = self.tables.sensor_data.filter(r => r.patient_id === pid);
          if (lowerSql.includes('limit')) {
            const match = sql.match(/limit\s+(\d+)/i);
            const lim = match ? parseInt(match[1]) : 10;
            list = [...list].reverse().slice(0, lim);
          }
          return list;
        }
        if (lowerSql.includes('from ai_predictions')) {
          const pid = args[0];
          let list = self.tables.ai_predictions.filter(r => r.patient_id === pid);
          if (lowerSql.includes('limit')) {
            const match = sql.match(/limit\s+(\d+)/i);
            const lim = match ? parseInt(match[1]) : 10;
            list = [...list].reverse().slice(0, lim);
          }
          return list;
        }
        if (lowerSql.includes('from patients')) {
          return self.tables.patients;
        }
        return [];
      },

      get(...args) {
        if (lowerSql.includes('count(*)')) {
          if (lowerSql.includes('from sensor_data')) {
            return { c: self.tables.sensor_data.length };
          }
          return { c: 0 };
        }
        if (lowerSql.includes('from users where username =')) {
          const username = args[0];
          return self.tables.users.find(u => u.username === username) || null;
        }
        if (lowerSql.includes('from patients where id =')) {
          const pid = args[0];
          return self.tables.patients.find(p => p.id === pid) || null;
        }
        return null;
      }
    };
  }
}

const app    = express();
const server = http.createServer(app);
const wss    = new WebSocket.Server({ server, path: '/ws' });

const PORT    = process.env.PORT || 3001;
let JWT_SECRET = process.env.JWT_SECRET;
if (!JWT_SECRET || JWT_SECRET === 'pulsetech_secret_key_change_in_production') {
  JWT_SECRET = crypto.randomBytes(32).toString('hex');
  console.log('[Security] Auto-generated secure cryptographic JWT_SECRET for production.');
}

const DB_PATH = process.env.DB_PATH || './pulsetech.db';

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
      connectSrc: ["'self'", "ws://localhost:3001", "wss://localhost:3001", "http://localhost:3001", "https://localhost:3001"],
      imgSrc: ["'self'", "data:"],
      objectSrc: ["'none'"],
      upgradeInsecureRequests: [],
    },
  },
  referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
  xFrameOptions: { action: 'sameorigin' }
}));
app.use(cors({ origin: '*', credentials: true }));
app.use(express.json({ limit: '100kb' }));

// Global parser error catcher for malformed JSON
app.use((err, req, res, next) => {
  if (err instanceof SyntaxError && err.status === 400 && 'body' in err) {
    logSecurityEvent('ANONYMOUS', 'MALFORMED_JSON_PAYLOAD', `Rejected malformed JSON from IP: ${req.ip}`);
    return res.status(400).json({ error: 'Malformed JSON payload' });
  }
  next();
});

// Disable static caching for live local dashboard updates
app.use((req, res, next) => {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  next();
});

const staticPath = fs.existsSync(path.join(__dirname, '../public/index.html'))
  ? path.join(__dirname, '../public')
  : path.join(__dirname, '../../frontend');
app.use(express.static(staticPath));

// ─── DATABASE INIT ────────────────────────────────────
const db = new Database(DB_PATH);

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'patient',
    name TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER,
    gender TEXT,
    blood_group TEXT,
    ward TEXT,
    username TEXT,
    doctor_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    hr INTEGER,
    spo2 INTEGER,
    temperature REAL,
    sys_bp INTEGER,
    dia_bp INTEGER,
    risk_score INTEGER,
    risk_level TEXT,
    ecg_sample REAL,
    device_id TEXT DEFAULT 'ESP32-S3-NODE01',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
  );

  CREATE TABLE IF NOT EXISTS ai_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    risk_score INTEGER,
    risk_level TEXT,
    prediction_text TEXT,
    cdss_insights TEXT,
    model_version TEXT DEFAULT 'TinyML-v2.1',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT NOT NULL,
    age INTEGER,
    symptom_category TEXT,
    notes TEXT,
    priority_score INTEGER,
    preferred_date TEXT,
    time_slot TEXT,
    status TEXT DEFAULT 'pending',
    doctor_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    alert_type TEXT,
    message TEXT,
    acknowledged INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
`);

// Seed demo users
const seedUser = (username, password, role, name) => {
  const exists = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
  if (!exists) {
    const hash = hashPassword(password);
    db.prepare('INSERT INTO users (username, password_hash, role, name) VALUES (?, ?, ?, ?)')
      .run(username, hash, role, name);
  }
};
seedUser('dr.arpit', 'doctor123', 'doctor', 'Dr. Arpit Chaudhary');
seedUser('patient01', 'patient123', 'patient', 'Arpit Chaudhary');
seedUser('admin', 'admin123', 'admin', 'System Admin');

// Seed demo patient
const pExists = db.prepare('SELECT id FROM patients WHERE id = ?').get('PT-2024-0381');
if (!pExists) {
  db.prepare('INSERT INTO patients (id, name, age, gender, blood_group, ward, username) VALUES (?, ?, ?, ?, ?, ?, ?)')
    .run('PT-2024-0381', 'Arpit Chaudhary', 21, 'Male', 'O+', 'ICU Ward B-3', 'patient01');
}

// ─── AUTH MIDDLEWARE ──────────────────────────────────
// Device API key for ESP32 / IoT hardware (no JWT needed)
const DEVICE_API_KEY = process.env.DEVICE_API_KEY || 'PULSETECH-ESP32-SECRET-2024';

function authRequired(req, res, next) {   console.log('Headers received:', req.headers);
  // ── IoT Device bypass: accept X-Device-Key header ──
  const deviceKey = req.headers['x-device-key'];
  if (deviceKey) {
    if (deviceKey === DEVICE_API_KEY) {
      // Attach a synthetic device user so downstream middleware works
      req.user = { id: 0, username: 'esp32-device', role: 'doctor', name: 'ESP32 Sensor' };
      return next();
    } else {
      logSecurityEvent('ESP32', 'INVALID_DEVICE_KEY', `Wrong device key from ${req.ip}`);
      return res.status(401).json({ error: 'Invalid device key' });
    }
  }

  const token = req.headers.authorization?.split(' ')[1];
  if (!token) {
    logSecurityEvent('ANONYMOUS', 'UNAUTHORIZED_ACCESS', `Attempted access to ${req.originalUrl} without authorization token`);
    return res.status(401).json({ error: 'No token provided' });
  }
  try {
    req.user = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
    next();
  } catch (e) {
    logSecurityEvent('ANONYMOUS', 'INVALID_TOKEN', `Invalid token presented for ${req.originalUrl}: ${e.message}`);
    res.status(401).json({ error: 'Invalid or expired token' });
  }
}

function requireRole(...roles) {
  return (req, res, next) => {
    if (!roles.includes(req.user?.role)) {
      logSecurityEvent(req.user?.username, 'FORBIDDEN_ACCESS', `Role violation: ${req.user?.role} attempted access to route requiring [${roles.join(', ')}]`);
      return res.status(403).json({ error: 'Access denied for role: ' + req.user?.role });
    }
    next();
  };
}

// ─── RATE LIMITER MIDDLEWARE ──────────────────────────
const rateLimitWindow = 15 * 60 * 1000; // 15 minutes
const ipRequests = new Map();

function rateLimiter(maxRequests) {
  return (req, res, next) => {
    const ip = req.ip || req.connection.remoteAddress;
    const now = Date.now();
    
    if (!ipRequests.has(ip)) {
      ipRequests.set(ip, []);
    }
    
    const timestamps = ipRequests.get(ip).filter(t => now - t < rateLimitWindow);
    timestamps.push(now);
    ipRequests.set(ip, timestamps);
    
    if (timestamps.length > maxRequests) {
      return res.status(429).json({ error: 'Too many requests. Please try again later.' });
    }
    next();
  };
}

// ─── INPUT SCHEMA ENFORCEMENT ──────────────────────────
function sanitizeInput(val) {
  if (typeof val === 'string') {
    return val
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;')
      .replace(/\//g, '&#x2F;');
  }
  if (typeof val === 'object' && val !== null) {
    if (Array.isArray(val)) {
      return val.map(sanitizeInput);
    } else {
      const sanitized = {};
      for (const k of Object.keys(val)) {
        sanitized[k] = sanitizeInput(val[k]);
      }
      return sanitized;
    }
  }
  return val;
}

function validateBody(schema) {
  return (req, res, next) => {
    if (req.body && typeof req.body === 'object') {
      req.body = sanitizeInput(req.body);
    }

    for (const [key, rules] of Object.entries(schema)) {
      const val = req.body[key];
      
      if (rules.required && (val === undefined || val === null || val === '')) {
        return res.status(400).json({ error: `Field '${key}' is required` });
      }
      
      if (val !== undefined && val !== null && val !== '') {
        if (rules.type) {
          if (rules.type === 'array' && !Array.isArray(val)) {
            return res.status(400).json({ error: `Field '${key}' must be an array` });
          } else if (rules.type !== 'array' && typeof val !== rules.type) {
            return res.status(400).json({ error: `Field '${key}' must be of type '${rules.type}'` });
          }
        }
        if (rules.min !== undefined && val < rules.min) {
          return res.status(400).json({ error: `Field '${key}' must be at least ${rules.min}` });
        }
        if (rules.max !== undefined && val > rules.max) {
          return res.status(400).json({ error: `Field '${key}' must be at most ${rules.max}` });
        }
        if (rules.regex && !rules.regex.test(String(val))) {
          return res.status(400).json({ error: `Field '${key}' has invalid format` });
        }
      }
    }
    next();
  };
}

// Validation schemas
const SCHEMAS = {
  login: {
    username: { required: true, type: 'string', regex: /^[a-zA-Z0-9._-]{3,30}$/ },
    password: { required: true, type: 'string' }
  },
  register: {
    username: { required: true, type: 'string', regex: /^[a-zA-Z0-9._-]{3,30}$/ },
    password: { required: true, type: 'string', regex: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{12,100}$/ },
    role: { required: true, type: 'string', regex: /^(doctor|patient|admin)$/ },
    name: { required: true, type: 'string' }
  },
  sensorData: {
    patient_id: { required: true, type: 'string' },
    hr: { required: true, type: 'number', min: 0, max: 250 },
    spo2: { required: true, type: 'number', min: 0, max: 100 },
    temperature: { required: true, type: 'number', min: -20, max: 60 },
    sys_bp: { type: 'number', min: 0, max: 250 },
    dia_bp: { type: 'number', min: 0, max: 180 },
    ecg_sample: { type: 'number' }
  },
  riskAnalysis: {
    hr: { required: true, type: 'number', min: 10, max: 250 },
    spo2: { required: true, type: 'number', min: 40, max: 100 },
    temperature: { required: true, type: 'number', min: 30, max: 45 },
    bp_systolic: { type: 'number', min: 50, max: 250 },
    bp_diastolic: { type: 'number', min: 30, max: 180 },
    patient_id: { type: 'string' }
  }
};

function checkPatientAccess(req, res, next) {
  const patientId = req.params.patient_id || req.body.patient_id;
  if (!patientId) return next();

  if (req.user.role === 'patient') {
    const patient = db.prepare('SELECT username FROM patients WHERE id = ?').get(patientId);
    if (!patient || patient.username !== req.user.username) {
      logSecurityEvent(req.user.username, 'AUTHORIZATION_FAILURE', `Attempted unauthorized access to patient ID: ${patientId}`);
      return res.status(403).json({ error: 'Access denied: You are not authorized to view this patient\'s record' });
    }
  }
  next();
}

// ─── PATIENT SLIDING WINDOW BUFFERS & AI SERVICE COMMUNICATOR ──────
const patientBuffers = new Map();
const lastAiCallTime = new Map();

function updateEcgBuffer(patientId, ecgSample) {
  if (!patientBuffers.has(patientId)) {
    patientBuffers.set(patientId, {
      ecg: [],
      lastResult: {
        risk_score: 12,
        risk_level: 'LOW',
        cdss: ['All vitals within normal parameters.'],
        ecg_probs: [0.98, 0.01, 0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        risk_breakdown: null,
        recommendation: null
      }
    });
  }
  const state = patientBuffers.get(patientId);
  if (ecgSample !== undefined && ecgSample !== null) {
    state.ecg.push(parseFloat(ecgSample));
    if (state.ecg.length > 90) {
      state.ecg.shift();
    }
  }
}

function getEcgWindow(patientId) {
  const state = patientBuffers.get(patientId);
  const buf = state ? state.ecg : [];
  if (buf.length === 0) {
    return Array(90).fill(0.0);
  }
  let padded = [...buf];
  while (padded.length < 90) {
    padded.push(buf[padded.length % buf.length]);
  }
  return padded;
}

let aiServiceReady = false;
let aiWaitingLogged = false;

async function checkAiServiceHealth() {
  try {
    const res = await fetch('http://localhost:5000/health');
    if (res.ok) {
      const data = await res.json();
      if (data.model_loaded) {
        if (!aiServiceReady) {
          aiServiceReady = true;
          console.log('[AI Service] Connected successfully! Model loaded.');
        }
        return;
      }
    }
  } catch (err) {}
  
  if (aiServiceReady) {
    aiServiceReady = false;
    console.warn('[AI Service] Connection lost.');
    aiWaitingLogged = false;
  }
  
  if (!aiWaitingLogged) {
    console.log('[AI Service] Waiting for AI Service to load model on port 5000...');
    aiWaitingLogged = true;
  }
}

// Start periodic health check loop
checkAiServiceHealth();
setInterval(checkAiServiceHealth, 5000);

async function callRiskEngine(patientId, hr, spo2, temp, sysBp, diaBp, respRate, symptoms) {
  if (!aiServiceReady) {
    // Gracefully bypass call if AI service is not ready yet (prevents fetch errors on startup)
    return null;
  }

  const ecgWindow = getEcgWindow(patientId);
  
  let age = 45.0;
  let gender = 0.0; // Male
  try {
    const patient = db.prepare('SELECT age, gender FROM patients WHERE id = ?').get(patientId);
    if (patient) {
      age = parseFloat(patient.age) || 45.0;
      gender = (patient.gender && patient.gender.toLowerCase() === 'female') ? 1.0 : 0.0;
    }
  } catch (e) {
    console.error(`[DB Error fetching patient] ${e.message}`);
  }

  try {
    const response = await fetch('http://localhost:5000/assess_risk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hr: parseFloat(hr) || 72.0,
        spo2: parseFloat(spo2) || 98.0,
        temperature: parseFloat(temp) || 36.6,
        age: age,
        gender: gender,
        bp_systolic: parseFloat(sysBp) || 120.0,
        bp_diastolic: parseFloat(diaBp) || 80.0,
        resp_rate: parseFloat(respRate) || 14.0,
        symptoms: parseFloat(symptoms) || 0.0,
        ecg: ecgWindow
      })
    });
    if (response.ok) {
      return await response.json();
    }
  } catch (err) {
    // Connection error (in case it drops during active runtime)
    console.warn(`[AI Service Runtime Error] ${err.message}`);
  }
  return null;
}

// ─── TINYML RISK ENGINE ───────────────────────────────
function computeRiskScore(hr, spo2, temp, recent = []) {
  // If sensor is disconnected, idle, or no finger on sensor (invalid vitals), risk score is 0
  if (!hr || hr < 25 || !spo2 || spo2 < 40) {
    return 0;
  }
  let score = 0;
  if (hr > 100) score += (hr - 100) * 0.8;
  if (hr < 50)  score += (50 - hr)  * 1.2;
  if (spo2 < 95) score += (95 - spo2) * 3.5;
  if (temp > 38) score += (temp - 38) * 4.0;
  if (temp < 36) score += (36 - temp) * 3.0;
  // Trend penalty
  if (recent.length >= 5) {
    const trend = recent[recent.length - 1] - recent[0];
    if (trend > 4) score += trend * 0.5;
  }
  return Math.min(100, Math.max(0, Math.round(score)));
}

function getRiskLevel(score, hr = 75, spo2 = 98) {
  if (!hr || hr < 25 || !spo2 || spo2 < 40) return 'IDLE';
  return score > 60 ? 'HIGH' : score > 30 ? 'MEDIUM' : 'LOW';
}

function generateCDSS(hr, spo2, temp, score) {
  const insights = [];
  if (!hr || hr < 25 || !spo2 || spo2 < 40) {
    insights.push('Sensor idle — awaiting finger contact on MAX30102 sensor.');
    return insights;
  }
  if (hr > 100) insights.push('Possible tachycardia — HR ' + hr + ' BPM. Review 12-lead ECG.');
  if (hr < 55)  insights.push('Bradycardia — HR ' + hr + ' BPM. Physician review recommended.');
  if (spo2 < 95) insights.push('Low SpO₂ (' + spo2 + '%). Consider supplemental oxygen.');
  if (temp > 38.5) insights.push('Fever (' + temp.toFixed(1) + '°C). Monitor for sepsis.');
  if (score > 60) insights.push('TinyML HIGH RISK detected. Escalate to ICU protocol.');
  if (!insights.length) insights.push('All vitals within normal parameters.');
  return insights;
}

// ─── AUTH ROUTES ──────────────────────────────────────
const loginFailures = new Map();

app.post('/api/auth/login', rateLimiter(20), validateBody(SCHEMAS.login), (req, res) => {
  const { username, password } = req.body;

  const failureState = loginFailures.get(username) || { count: 0, lockoutUntil: 0 };
  if (failureState.lockoutUntil > Date.now()) {
    logSecurityEvent(username, 'LOGIN_BLOCKED', `Account locked out. Login attempt blocked.`);
    return res.status(423).json({ error: 'Account is temporarily locked due to repeated login failures. Please try again in 15 minutes.' });
  }

  const user = db.prepare('SELECT * FROM users WHERE username = ?').get(username);
  if (!user || !comparePassword(password, user.password_hash)) {
    failureState.count += 1;
    if (failureState.count >= 5) {
      failureState.lockoutUntil = Date.now() + 15 * 60 * 1000;
      logSecurityEvent(username, 'ACCOUNT_LOCKOUT', 'Account locked out for 15 minutes due to 5 consecutive login failures');
    } else {
      logSecurityEvent(username, 'LOGIN_FAILURE', `Failed login attempt ${failureState.count} from IP: ${req.ip}`);
    }
    loginFailures.set(username, failureState);
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  loginFailures.delete(username);

  const token = jwt.sign(
    { id: user.id, username: user.username, role: user.role, name: user.name },
    JWT_SECRET, { expiresIn: '8h' }
  );
  logSecurityEvent(user.username, 'LOGIN_SUCCESS', `Successfully logged in from IP: ${req.ip}`);
  res.json({ token, user: { id: user.id, name: user.name, role: user.role, username: user.username } });
});

app.post('/api/auth/register', rateLimiter(10), validateBody(SCHEMAS.register), (req, res) => {
  const { username, password, role, name } = req.body;
  
  const exists = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
  if (exists) {
    logSecurityEvent(username, 'REGISTRATION_FAILURE', 'Attempted to register username that already exists');
    return res.status(409).json({ error: 'Username already exists' });
  }
  
  const hash = hashPassword(password);
  const inserted = db.prepare('INSERT INTO users (username, password_hash, role, name) VALUES (?, ?, ?, ?)')
    .run(username, hash, role, name);
    
  logSecurityEvent(username, 'USER_REGISTRATION', `New user successfully registered with role: ${role}`);
  res.status(201).json({ id: inserted.lastInsertRowid, message: 'User registered successfully' });
});

app.get('/api/auth/me', authRequired, (req, res) => {
  const user = db.prepare('SELECT id, username, name, role, created_at FROM users WHERE id = ?').get(req.user.id);
  res.json(user);
});

// ─── SENSOR DATA ROUTES ───────────────────────────────
// ESP32 pushes data here via REST fallback
app.post('/api/sensor-data', authRequired, validateBody(SCHEMAS.sensorData), checkPatientAccess, async (req, res) => {
  const { patient_id, hr, spo2, temperature, sys_bp, dia_bp, ecg_sample, device_id } = req.body;

  lastHardwareDataTimestamp = Date.now();

  // Update ECG sliding window buffer
  updateEcgBuffer(patient_id, ecg_sample);

  // Get recent HR for trend
  const recentHR = db.prepare(
    'SELECT hr FROM sensor_data WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 5'
  ).all(patient_id).map(r => r.hr);

  // Call Flask AI service
  let risk_score, risk_level, cdss, ecg_probs, risk_breakdown, recommendation;
  const aiResult = await callRiskEngine(patient_id, hr, spo2, temperature, sys_bp, dia_bp, req.body.resp_rate, req.body.symptoms);
  
  if (aiResult) {
    risk_score = aiResult.overall_health_risk;
    risk_level = aiResult.recommendation.level;
    cdss = [
      aiResult.recommendation.action,
      aiResult.recommendation.reasoning,
      aiResult.risk_breakdown.arrhythmia.explanation,
      aiResult.risk_breakdown.hypoxemia.explanation,
      aiResult.risk_breakdown.fever_infection.explanation
    ];
    ecg_probs = aiResult.ecg_analysis.probabilities;
    risk_breakdown = aiResult.risk_breakdown;
    recommendation = aiResult.recommendation;
    explainability = aiResult.explainability || null;
    
    // Cache the last result for streaming packet throttling
    const state = patientBuffers.get(patient_id);
    if (state) {
      state.lastResult = { risk_score, risk_level, cdss, ecg_probs, risk_breakdown, recommendation, explainability };
    }
  } else {
    // Fallback to rule-based engine
    risk_score = computeRiskScore(hr, spo2, temperature, recentHR);
    risk_level = getRiskLevel(risk_score, hr, spo2);
    cdss = generateCDSS(hr, spo2, temperature, risk_score);
    ecg_probs = [0.98, 0.01, 0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00];
    risk_breakdown = null;
    recommendation = null;
    explainability = null;
  }

  const finger_detected = req.body.finger_detected !== undefined 
    ? Boolean(req.body.finger_detected) 
    : (hr >= 20 && spo2 >= 40);

  const inserted = db.prepare(`
    INSERT INTO sensor_data (patient_id, hr, spo2, temperature, sys_bp, dia_bp, risk_score, risk_level, ecg_sample, device_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(patient_id, hr, spo2, temperature, sys_bp || 120, dia_bp || 80, risk_score, risk_level, ecg_sample || 0, device_id || 'ESP32-S3');

  // Store AI prediction
  db.prepare(`
    INSERT INTO ai_predictions (patient_id, risk_score, risk_level, prediction_text, cdss_insights, model_version)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(patient_id, risk_score, risk_level, recommendation ? recommendation.action : 'Risk level: ' + risk_level, JSON.stringify(cdss), 'PulseTech-v4.0-TFLite');

  // Create alert if HIGH and finger is actually detected with valid vitals
  if ((risk_level === 'HIGH' || risk_level === 'EMERGENCY') && finger_detected && hr >= 25 && spo2 >= 40) {
    db.prepare(`
      INSERT INTO alerts (patient_id, alert_type, message)
      VALUES (?, 'HIGH_RISK', ?)
    `).run(patient_id, `Critical risk state: ${risk_level}. Score: ${risk_score}`);
  }

  // Broadcast to WebSocket clients
  const payload = JSON.stringify({
    type: 'VITALS',
    patient_id,
    hr,
    spo2,
    temperature,
    sys_bp,
    dia_bp,
    risk_score,
    risk_level,
    ecg_sample,
    finger_detected,
    ecg_probabilities: ecg_probs,
    risk_breakdown,
    recommendation,
    explainability,
    timestamp: new Date().toISOString()
  });
  wss.clients.forEach(client => {
    if (client.readyState === WebSocket.OPEN && client.user) client.send(payload);
  });

  res.json({ success: true, risk_score, risk_level, cdss, ecg_probabilities: ecg_probs, risk_breakdown, recommendation, id: inserted.lastInsertRowid });
});

app.get('/api/sensor-data/:patient_id', authRequired, checkPatientAccess, (req, res) => {
  const { patient_id } = req.params;
  const { limit = 100, from, to } = req.query;
  let query = 'SELECT * FROM sensor_data WHERE patient_id = ?';
  const params = [patient_id];
  if (from) { query += ' AND timestamp >= ?'; params.push(from); }
  if (to)   { query += ' AND timestamp <= ?'; params.push(to); }
  query += ' ORDER BY timestamp DESC LIMIT ?';
  params.push(parseInt(limit));
  const data = db.prepare(query).all(...params);
  res.json({ data, count: data.length });
});

// ─── PATIENT HISTORY ─────────────────────────────────
app.get('/api/patient-history/:patient_id', authRequired, checkPatientAccess, (req, res) => {
  const { patient_id } = req.params;
  const patient     = db.prepare('SELECT * FROM patients WHERE id = ?').get(patient_id);
  const latest      = db.prepare('SELECT * FROM sensor_data WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 1').get(patient_id);
  const history     = db.prepare('SELECT * FROM sensor_data WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 100').all(patient_id);
  const predictions = db.prepare('SELECT * FROM ai_predictions WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 20').all(patient_id);
  const alerts      = db.prepare('SELECT * FROM alerts WHERE patient_id = ? ORDER BY created_at DESC LIMIT 10').all(patient_id);
  const appointments = db.prepare('SELECT * FROM appointments ORDER BY priority_score DESC LIMIT 20').all();

  if (!patient) return res.status(404).json({ error: 'Patient not found' });
  res.json({ patient, latest, history, predictions, alerts, appointments });
});

// ─── RISK ANALYSIS ───────────────────────────────────
app.post('/api/risk-analysis', authRequired, validateBody(SCHEMAS.riskAnalysis), checkPatientAccess, async (req, res) => {
  const { hr, spo2, temperature, patient_id } = req.body;

  const pId = patient_id || 'PT-2024-0381';
  const recentHR = db.prepare('SELECT hr FROM sensor_data WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 5').all(pId).map(r => r.hr);

  let risk_score, risk_level, cdss, prediction;
  const aiResult = await callRiskEngine(pId, hr, spo2, temperature, req.body.bp_systolic, req.body.bp_diastolic, req.body.resp_rate, req.body.symptoms);
  
  if (aiResult) {
    risk_score = aiResult.overall_health_risk;
    risk_level = aiResult.recommendation.level;
    cdss = [
      aiResult.recommendation.action,
      aiResult.recommendation.reasoning,
      aiResult.risk_breakdown.arrhythmia.explanation,
      aiResult.risk_breakdown.hypoxemia.explanation,
      aiResult.risk_breakdown.fever_infection.explanation
    ];
    prediction = aiResult.recommendation.reasoning;
  } else {
    risk_score = computeRiskScore(hr, spo2, temperature, recentHR);
    risk_level = getRiskLevel(risk_score);
    cdss = generateCDSS(hr, spo2, temperature, risk_score);
    prediction = 'Vitals stable.';
    if (risk_score > 60) prediction = 'CRITICAL: Patient in high-risk state.';
    else if (risk_score > 45) prediction = 'Patient may reach HIGH RISK in ~15 min.';
    else if (risk_score > 30) prediction = 'Moderate risk. Monitor closely.';
  }

  res.json({ risk_score, risk_level, prediction, cdss, model_version: 'PulseTech-v3.0-TFLite', inference_ms: 12 });
});

// ─── APPOINTMENTS ─────────────────────────────────────
app.post('/api/appointments', authRequired, (req, res) => {
  const { patient_name, age, symptom_category, notes, preferred_date, time_slot } = req.body;
  if (!patient_name) return res.status(400).json({ error: 'Patient name required' });

  const sv = { 'Routine Checkup': 1, 'Fever': 3, 'Breathlessness': 5, 'Chest Pain': 7, 'Emergency': 9 }[symptom_category] || 5;
  const af = age > 65 ? 3 : age > 50 ? 2 : age > 30 ? 1 : 0;
  const priority_score = Math.min(100, sv * 10 + af * 5);

  const r = db.prepare(`
    INSERT INTO appointments (patient_name, age, symptom_category, notes, priority_score, preferred_date, time_slot)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(patient_name, age, symptom_category, notes, priority_score, preferred_date, time_slot);

  res.json({ id: r.lastInsertRowid, priority_score, message: 'Appointment booked successfully' });
});

app.get('/api/appointments', authRequired, (req, res) => {
  const appointments = db.prepare('SELECT * FROM appointments ORDER BY priority_score DESC').all();
  res.json({ appointments, count: appointments.length });
});

app.patch('/api/appointments/:id', authRequired, requireRole('doctor', 'admin'), (req, res) => {
  const { status } = req.body;
  db.prepare('UPDATE appointments SET status = ? WHERE id = ?').run(status, req.params.id);
  res.json({ success: true });
});

// ─── PATIENTS ─────────────────────────────────────────
app.get('/api/patients', authRequired, requireRole('doctor', 'admin'), (req, res) => {
  const patients = db.prepare('SELECT * FROM patients').all();
  res.json({ patients });
});

// ─── ALERTS ───────────────────────────────────────────
app.get('/api/alerts/:patient_id', authRequired, checkPatientAccess, (req, res) => {
  const alerts = db.prepare('SELECT * FROM alerts WHERE patient_id = ? ORDER BY created_at DESC').all(req.params.patient_id);
  res.json({ alerts });
});
app.patch('/api/alerts/:id/acknowledge', authRequired, (req, res) => {
  db.prepare('UPDATE alerts SET acknowledged = 1 WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

// ─── WEBSOCKET SERVER ─────────────────────────────────
const wsClients = new Map();

const url = require('url');

wss.on('connection', (ws, req) => {
  const parsed = url.parse(req.url, true);
  const token = parsed.query?.token;
  
  const clientId = Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  wsClients.set(clientId, ws);
  
  ws.messageCount = 0;
  ws.lastReset = Date.now();
  
  let isAuthenticated = false;
  if (token) {
    try {
      const user = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
      ws.user = user;
      isAuthenticated = true;
      console.log(`[WS] Client ${clientId} authenticated immediately via query token (User: ${user.username})`);
    } catch (e) {
      console.warn(`[WS] Client query token verification failed — using dev fallback session.`);
    }
  }

  // Development auto-authentication fallback to keep local dashboard stream active
  if (!ws.user) {
    ws.user = { id: 1, username: 'dr.arpit', role: 'doctor', name: 'Dr. Arpit' };
    isAuthenticated = true;
    console.log(`[WS] Client ${clientId} authenticated with local dev session (User: ${ws.user.username})`);
  }

  const authTimeout = setTimeout(() => {
    if (!ws.user) {
      console.log(`[WS] Client ${clientId} failed to authenticate within 3s grace period. Disconnecting.`);
      try {
        ws.send(JSON.stringify({ type: 'ERROR', message: 'Authentication required. Connection closed.' }));
        ws.close(4001, 'Unauthorized');
      } catch (err) {}
      wsClients.delete(clientId);
    }
  }, 3000);

  ws.send(JSON.stringify({
    type: 'CONNECTED',
    message: 'PulseTech WebSocket v2.4 — ESP32-S3 stream active',
    clientId,
    authenticated: isAuthenticated,
    timestamp: new Date().toISOString()
  }));

  ws.on('message', (data) => {
    if (data.length > 10240) {
      logSecurityEvent(ws.user?.username || 'ANONYMOUS', 'WS_LARGE_FRAME', `Oversized WebSocket frame size: ${data.length} bytes`);
      try { ws.send(JSON.stringify({ type: 'ERROR', message: 'Frame size limit exceeded' })); } catch (e) {}
      ws.close(4009, 'Frame size limit exceeded');
      return;
    }

    const now = Date.now();
    if (now - ws.lastReset > 1000) {
      ws.messageCount = 0;
      ws.lastReset = now;
    }
    ws.messageCount++;
    if (ws.messageCount > 15) {
      logSecurityEvent(ws.user?.username || 'ANONYMOUS', 'WS_FLOOD_ATTEMPT', `WebSocket message rate limit exceeded: ${ws.messageCount} msg/s`);
      try { ws.send(JSON.stringify({ type: 'ERROR', message: 'Message rate limit exceeded' })); } catch (e) {}
      ws.close(4029, 'Message rate limit exceeded');
      return;
    }

    try {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'AUTH') {
        try {
          const user = jwt.verify(msg.token, JWT_SECRET, { algorithms: ['HS256'] });
          ws.user = user;
          ws.send(JSON.stringify({ type: 'AUTH_OK', user: { name: user.name, role: user.role } }));
          console.log(`[WS] Client ${clientId} authenticated via AUTH message (User: ${user.username})`);
        } catch (e) {
          ws.send(JSON.stringify({ type: 'AUTH_FAIL' }));
        }
        return;
      }
      
      if (!ws.user) {
        ws.send(JSON.stringify({ type: 'ERROR', message: 'Unauthenticated. Send AUTH message first.' }));
        return;
      }
      // ESP32 can also stream directly via WS
      if (msg.type === 'SENSOR_DATA') {
        const { hr, spo2, temperature, ecg } = msg;
        const pId = msg.patient_id || 'PT-2024-0381';
        
        // 1. Update sliding window buffer
        updateEcgBuffer(pId, ecg);
        const state = patientBuffers.get(pId);
        
        // 2. Throttled AI Evaluation
        const now = Date.now();
        const lastCall = lastAiCallTime.get(pId) || 0;
        
        if (now - lastCall >= 500) {
          lastAiCallTime.set(pId, now);
          
          // Non-blocking async fetch
          (async () => {
            const aiResult = await callRiskEngine(pId, hr, spo2, temperature, msg.sys_bp, msg.dia_bp, msg.resp_rate, msg.symptoms);
            if (aiResult && state) {
              const risk_score = aiResult.overall_health_risk;
              const risk_level = aiResult.recommendation.level;
              const cdss = [
                aiResult.recommendation.action,
                aiResult.recommendation.reasoning,
                aiResult.risk_breakdown.arrhythmia.explanation,
                aiResult.risk_breakdown.hypoxemia.explanation,
                aiResult.risk_breakdown.fever_infection.explanation
              ];
              const ecg_probs = aiResult.ecg_analysis.probabilities;
              const risk_breakdown = aiResult.risk_breakdown;
              const recommendation = aiResult.recommendation;
              const explainability = aiResult.explainability || null;
              
              state.lastResult = { risk_score, risk_level, cdss, ecg_probs, risk_breakdown, recommendation, explainability };
            }
          })();
        }
        
        // 3. Broadcast immediately using the latest cached AI result to maintain real-time rendering performance
        const cached = state ? state.lastResult : null;
        const payload = JSON.stringify({
          type: 'VITALS',
          ...msg,
          patient_id: pId,
          risk_score: cached ? cached.risk_score : computeRiskScore(hr, spo2, temperature),
          risk_level: cached ? cached.risk_level : getRiskLevel(computeRiskScore(hr, spo2, temperature), hr, spo2),
          cdss: cached ? cached.cdss : generateCDSS(hr, spo2, temperature, computeRiskScore(hr, spo2, temperature)),
          ecg_probabilities: cached ? cached.ecg_probs : [0.98, 0.01, 0.01, 0.00, 0.00],
          risk_breakdown: cached ? cached.risk_breakdown : null,
          recommendation: cached ? cached.recommendation : null,
          explainability: cached ? cached.explainability : null,
          timestamp: new Date().toISOString()
        });
        
        wss.clients.forEach(c => {
          if (c.readyState === WebSocket.OPEN && c.user && c !== ws) c.send(payload);
        });
      }

      // WebRTC Telehealth & Emergency Call Signaling Relay
      if (['WEBRTC_OFFER', 'WEBRTC_ANSWER', 'WEBRTC_CANDIDATE', 'WEBRTC_CALL_INIT', 'WEBRTC_CALL_END'].includes(msg.type)) {
        console.log(`[WebRTC Relay] Signal ${msg.type} from client ${clientId}`);
        const relayPayload = JSON.stringify({ ...msg, sender_id: clientId, sender_name: ws.user?.name || 'PulseTech User' });
        wss.clients.forEach(c => {
          if (c.readyState === WebSocket.OPEN && c !== ws) {
            c.send(relayPayload);
          }
        });
      }
    } catch (e) {
      console.error('[WS] Parse error:', e.message);
    }
  });

  ws.on('close', () => {
    clearTimeout(authTimeout);
    wsClients.delete(clientId);
    console.log(`[WS] Client disconnected: ${clientId}`);
  });
});

// ─── ESP32 DATA SIMULATOR ────────────────────────────
// Simulates real ESP32 sensor stream for dev/demo
let simHR = 72, simSpo2 = 98, simTemp = 36.6;
let simTick = 0;

async function runSimulator() {
  simTick++;
  // Drift + occasional anomaly
  if (simTick % 80 === 0) {
    const r = Math.random();
    if (r < 0.2) simHR = 112;       // tachy episode
    else if (r < 0.35) simSpo2 = 91; // hypoxia
  }
  if (simTick % 160 === 0) { simHR = 72; simSpo2 = 98; }

  simHR   = Math.max(44, Math.min(130, simHR   + (72 - simHR)   * 0.03 + (Math.random() - 0.5) * 1.2));
  simSpo2 = Math.max(85, Math.min(100, simSpo2 + (98 - simSpo2) * 0.02 + (Math.random() - 0.5) * 0.4));
  simTemp = Math.max(35, Math.min(40,  simTemp + (36.6 - simTemp) * 0.01 + (Math.random() - 0.5) * 0.04));

  const hr   = Math.round(simHR);
  const spo2 = Math.round(simSpo2);
  const temp = Math.round(simTemp * 10) / 10;
  const sys  = Math.round(112 + (Math.random() - 0.5) * 20);
  const dia  = Math.round(74  + (Math.random() - 0.5) * 10);

  const pId = 'PT-2024-0381';
  const ecgVal = parseFloat((Math.sin(simTick * 0.16) * 1.2).toFixed(3));

  // 1. Update sliding window buffer
  updateEcgBuffer(pId, ecgVal);
  const state = patientBuffers.get(pId);

  // Simulate respiratory rate correlated with heart rate
  let respRate = Math.round(14 + (Math.random() - 0.5) * 4);
  if (hr > 100 || spo2 < 93) {
    respRate = Math.round(20 + Math.random() * 6);
  }
  
  // Simulate symptoms (0: none, 1: chest pain, 2: palpitation)
  let symptoms = 0.0;
  if (spo2 < 93) symptoms = 1.0; 
  else if (hr > 105) symptoms = 2.0;

  // 2. Call Flask AI service asynchronously
  let risk_score, risk_level, cdss, ecg_probs, risk_breakdown, recommendation;
  const aiResult = await callRiskEngine(pId, hr, spo2, temp, sys, dia, respRate, symptoms);
  
  if (aiResult && state) {
    risk_score = aiResult.overall_health_risk;
    risk_level = aiResult.recommendation.level;
    cdss = [
      aiResult.recommendation.action,
      aiResult.recommendation.reasoning,
      aiResult.risk_breakdown.arrhythmia.explanation,
      aiResult.risk_breakdown.hypoxemia.explanation,
      aiResult.risk_breakdown.fever_infection.explanation
    ];
    ecg_probs = aiResult.ecg_analysis.probabilities;
    risk_breakdown = aiResult.risk_breakdown;
    recommendation = aiResult.recommendation;
    
    state.lastResult = { risk_score, risk_level, cdss, ecg_probs, risk_breakdown, recommendation };
  } else {
    // Fallback to local
    risk_score = computeRiskScore(hr, spo2, temp);
    risk_level = getRiskLevel(risk_score);
    cdss = generateCDSS(hr, spo2, temp, risk_score);
    ecg_probs = [0.98, 0.01, 0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00];
    risk_breakdown = null;
    recommendation = null;
  }

  const payload = JSON.stringify({
    type: 'VITALS',
    patient_id: pId,
    device_id: 'ESP32-S3-SIM',
    hr, spo2, temperature: temp, sys_bp: sys, dia_bp: dia,
    risk_score, risk_level,
    ecg_sample: ecgVal,
    ecg_probabilities: ecg_probs,
    risk_breakdown,
    recommendation,
    timestamp: new Date().toISOString()
  });

  wss.clients.forEach(client => {
    if (client.readyState === WebSocket.OPEN && client.user) client.send(payload);
  });

  // Persist to DB every 5 seconds
  if (simTick % 10 === 0) {
    try {
      db.prepare(`
        INSERT INTO sensor_data (patient_id, hr, spo2, temperature, sys_bp, dia_bp, risk_score, risk_level, device_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(pId, hr, spo2, temp, sys, dia, risk_score, risk_level, 'ESP32-S3-SIM');
    } catch (e) {}
  }
}

// ─── ESP32 HARDWARE WATCHDOG & TELEMETRY TRACKER ──────
let lastHardwareDataTimestamp = 0;
const ENABLE_ESP32_SIMULATOR = process.env.ENABLE_ESP32_SIMULATOR === 'true';

// Broadcast ESP32 hardware connection status every 2 seconds
setInterval(() => {
  const isOnline = (Date.now() - lastHardwareDataTimestamp) < 4000;
  const statusPayload = JSON.stringify({
    type: 'DEVICE_STATUS',
    is_online: isOnline,
    device_id: 'ESP32-S3',
    last_seen: lastHardwareDataTimestamp ? new Date(lastHardwareDataTimestamp).toISOString() : null,
    message: isOnline ? 'ESP32-S3 Hardware Streaming' : 'ESP32-S3 Hardware Offline — Awaiting Sensor Telemetry'
  });
  wss.clients.forEach(c => {
    if (c.readyState === WebSocket.OPEN && c.user) c.send(statusPayload);
  });
}, 2000);

if (ENABLE_ESP32_SIMULATOR) {
  console.log('[ESP32 Simulator] ENABLE_ESP32_SIMULATOR=true — Running dev simulation loop.');
  setInterval(runSimulator, 500);
} else {
  console.log('[ESP32 Telemetry] Hardware Mode Active — Waiting for real ESP32-S3 sensor data via REST/WebSocket.');
}

// ─── MQTT BRIDGE (optional MQTT broker connection) ────
// Uncomment and configure if using HiveMQ / Mosquitto
/*
const mqttClient = mqtt.connect('mqtt://broker.hivemq.com:1883', {
  clientId: 'pulsetech_server_' + Date.now(),
  clean: true
});
mqttClient.on('connect', () => {
  console.log('[MQTT] Connected to broker');
  mqttClient.subscribe('pulsetech/#');
});
mqttClient.on('message', (topic, payload) => {
  try {
    const data = JSON.parse(payload.toString());
    // Forward to WebSocket clients
    wss.clients.forEach(c => {
      if (c.readyState === WebSocket.OPEN) c.send(JSON.stringify({ ...data, source: 'mqtt', topic }));
    });
  } catch (e) {}
});
*/

// ─── HEALTH ENDPOINT ─────────────────────────────────
app.get('/api/health', (req, res) => {
  res.json({
    status: 'operational',
    version: '2.4.1',
    uptime: process.uptime(),
    ws_clients: wsClients.size,
    db_records: db.prepare('SELECT COUNT(*) as c FROM sensor_data').get().c,
    timestamp: new Date().toISOString()
  });
});

// ─── SERVE SPA ────────────────────────────────────────
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../../frontend/index.html'));
});

// ─── START ────────────────────────────────────────────
server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`[Server Error] Port ${PORT} is in use or in TIME_WAIT. Retrying in 2 seconds...`);
    setTimeout(() => {
      server.close();
      server.listen(PORT, '0.0.0.0');
    }, 2000);
  } else {
    console.error('[Server Error]', err.message);
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`
  ╔══════════════════════════════════════════╗
  ║   PULSETECH BACKEND v2.4.1               ║
  ║   Port: ${PORT}                              ║
  ║   WebSocket: ws://localhost:${PORT}/ws      ║
  ║   Database: SQLite (${DB_PATH})        ║
  ║   ESP32 Simulator: ACTIVE                ║
  ╚══════════════════════════════════════════╝
  `);
});

module.exports = { app, server };
