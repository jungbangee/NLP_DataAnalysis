require('dotenv').config({ path: require('path').join(__dirname, '.env') });
const express   = require('express');
const session   = require('express-session');
const path      = require('path');
const multer    = require('multer');
const fs        = require('fs');
const readline  = require('readline');
const { spawn } = require('child_process');
const mongoose  = require('mongoose');

// ── 메타데이터 CSV 캐시 ────────────────────────────────────────
// key: "date|course_id" → {instructor, course_name, subject, ...}
let metaCache = {};

async function parseCSVToRows(csvPath) {
  const rows = [];
  const rl = readline.createInterface({ input: fs.createReadStream(csvPath, 'utf8') });
  let headers = null;
  for await (const line of rl) {
    const trimmed = line.replace(/^﻿/, '').trim();
    if (!trimmed) continue;
    const cols = trimmed.split(',').map(c => c.trim());
    if (!headers) { headers = cols; continue; }
    const row = {};
    headers.forEach((h, i) => { row[h] = cols[i] || ''; });
    if (row.date && row.course_id) rows.push(row);
  }
  return rows;
}

async function loadMetaCSV(csvPath) {
  if (!fs.existsSync(csvPath)) return;
  const rows = await parseCSVToRows(csvPath);

  // MongoDB에 upsert (date+course_id 기준)
  let upserted = 0;
  for (const row of rows) {
    await Meta.findOneAndUpdate(
      { date: row.date, course_id: row.course_id },
      {
        date:           row.date,
        course_id:      row.course_id,
        course_name:    row.course_name    || '',
        instructor:     row.instructor     || '',
        sub_instructor: row.sub_instructor || '',
        subject:        row.subject        || '',
        content:        row.content        || '',
        time:           row.time           || '',
      },
      { upsert: true, new: true }
    );
    upserted++;
  }

  await refreshMetaCache();
  console.log(`✅ 메타데이터 DB 저장: ${upserted}개 upsert 완료`);
}

async function refreshMetaCache() {
  const all = await Meta.find({}).lean();
  metaCache = {};
  all.forEach(doc => {
    const key = `${doc.date}|${doc.course_id}`;
    if (!metaCache[key]) metaCache[key] = doc;
  });
  return Object.keys(metaCache).length;
}

function lookupMeta(date, courseId) {
  return metaCache[`${date}|${courseId}`] || null;
}

const app  = express();
const PORT = process.env.PORT || 3000;

// ── MongoDB 연결 ───────────────────────────────────────────────
const MONGO_URI = process.env.MONGO_URI || 'mongodb://127.0.0.1:27017/nlp_lecture';

mongoose.connect(MONGO_URI)
  .then(() => console.log('✅ MongoDB 연결 성공:', MONGO_URI))
  .catch(err => {
    console.error('❌ MongoDB 연결 실패:', err.message);
    console.error('   MongoDB 서비스가 실행 중인지 확인하세요.');
    console.error('   Windows: net start MongoDB');
    process.exit(1);
  });

// ── MongoDB 스키마 ─────────────────────────────────────────────
// ── 일별 요약 스키마 ──────────────────────────────────────────
const dailySummarySchema = new mongoose.Schema({
  date:        { type: String, required: true, index: true },
  course_id:   { type: String, required: true, index: true },
  instructor:  { type: String, default: '', index: true },
  status:      { type: String, default: '' },
  categories:  { type: mongoose.Schema.Types.Mixed },
  anchors:     { type: mongoose.Schema.Types.Mixed },
  overall:     { type: mongoose.Schema.Types.Mixed },
  daily_review:{ type: String, default: '' },
  strengths:   { type: [String] },
  improvements:{ type: [String] },
  model:       { type: String },
  tokens:      { type: mongoose.Schema.Types.Mixed },
  cost_usd:    { type: Number },
  generated_at:{ type: Date, default: Date.now },
}, { timestamps: true });

dailySummarySchema.index({ date: 1, course_id: 1 }, { unique: true });
const DailySummary = mongoose.model('DailySummary', dailySummarySchema);

// ── 강사 종합평가 스키마 ─────────────────────────────────────
const instructorSummarySchema = new mongoose.Schema({
  instructor:        { type: String, required: true, index: true },
  course_id:         { type: String, default: '' },
  n_lectures:        { type: Number },
  date_range:        { type: [String] },
  proficiency_grade: { type: String },
  headline:          { type: String },
  stats:             { type: mongoose.Schema.Types.Mixed },
  profile_summary:   { type: String },
  consistency_note:  { type: String },
  trajectory_note:   { type: String },
  systematic_strengths:  { type: [String] },
  systematic_weaknesses: { type: [String] },
  development_goals:     { type: [String] },
  priority_rationale:    { type: String },
  strength_leverage:     { type: String },
  validity_caveats:      { type: String },
  model:             { type: String },
  tokens:            { type: mongoose.Schema.Types.Mixed },
  cost_usd:          { type: Number },
  generated_at:      { type: Date, default: Date.now },
}, { timestamps: true });

instructorSummarySchema.index({ instructor: 1, course_id: 1 });
const InstructorSummary = mongoose.model('InstructorSummary', instructorSummarySchema);

// ── 메타데이터 스키마 ─────────────────────────────────────────
const metaSchema = new mongoose.Schema({
  date:         { type: String, required: true },
  course_id:    { type: String, required: true },
  course_name:  { type: String, default: '' },
  instructor:   { type: String, default: '' },
  sub_instructor: { type: String, default: '' },
  subject:      { type: String, default: '' },
  content:      { type: String, default: '' },
  time:         { type: String, default: '' },
}, { timestamps: true });

metaSchema.index({ date: 1, course_id: 1 }, { unique: true });
const Meta = mongoose.model('Meta', metaSchema);

const categoryResultSchema = new mongoose.Schema({
  timestamp:  { type: Date,   default: Date.now, index: true },
  filename:   { type: String, required: true },
  date:       { type: String, index: true },
  course_id:  { type: String, index: true },
  instructor: { type: String, default: '' },
  category:   { type: String, required: true, index: true }, // cate1~cate5
  items:      { type: mongoose.Schema.Types.Mixed },
  error:      { type: String, default: '' },
}, { timestamps: true });

categoryResultSchema.index({ date: 1, course_id: 1, category: 1 }, { unique: true });
const CategoryResult = mongoose.model('CategoryResult', categoryResultSchema);

// ── 폴더 초기화 ───────────────────────────────────────────────
const UPLOAD_DIR = path.join(__dirname, 'uploads');
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

// ── 미들웨어 ─────────────────────────────────────────────────
app.use(express.urlencoded({ extended: true, limit: '50mb' }));
app.use(express.json({ limit: '50mb' }));
app.use(session({ secret: 'nlp-secret-key', resave: false, saveUninitialized: true }));
app.use(express.static(path.join(__dirname, 'public')));

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, UPLOAD_DIR),
  filename: (req, file, cb) => {
    // 임시파일에 .txt 확장자 유지 (Python 스크립트가 .txt 여부를 체크함)
    const unique = Date.now() + '_' + Math.round(Math.random() * 1e6);
    cb(null, unique + '.txt');
  },
});

const upload = multer({
  storage,
  fileFilter: (req, file, cb) => {
    if (file.originalname.endsWith('.txt') || file.mimetype === 'text/plain') cb(null, true);
    else cb(new Error('.txt 파일만 업로드 가능합니다.'));
  },
  limits: { fileSize: 20 * 1024 * 1024 },
});

function requireAuth(req, res, next) {
  if (req.session?.user) return next();
  res.redirect('/');
}

// ── 카테고리별 Python 스크립트 경로 매핑 ─────────────────────
// cate4 후보 경로 (존재하는 파일 자동 선택)
function resolveCate4Script() {
  const candidates = [
    path.join(__dirname, 'cate4', 'cate4_analyze_lecture.py'),
    path.join(__dirname, 'cate4', 'analyze_lecture.py'),
    path.join(__dirname, 'cate4', 'analyze_lecture_test.py'),
    path.join(__dirname, 'cate4', 'test_web.py'),
    path.join(__dirname, 'cate4', 'main.py'),
  ];
  return candidates.find(p => fs.existsSync(p)) || candidates[0];
}

const CATE_SCRIPTS = [
  { key: 'cate1', script: path.join(__dirname, 'cate1,5', 'lecture_analyzer.py'), label: '① 언어 표현 품질' },
  { key: 'cate2', script: path.join(__dirname, 'cate2',   'v8_unified.py'),        label: '② 강의 도입 및 구조' },
  { key: 'cate3', script: path.join(__dirname, 'cate3',   'main.py'),              label: '③ 개념 설명 명확성' },
  { key: 'cate4', script: resolveCate4Script(),                                    label: '④ 예시 및 실습 연계' },
  { key: 'cate5', script: path.join(__dirname, 'cate1,5', 'lecture_analyzer.py'), label: '⑤ 수강생 상호작용' },
];

// ── stdout에서 첫 번째 완전한 JSON 객체 추출 ─────────────────
function extractFirstJson(str) {
  let start = -1, depth = 0, inStr = false, esc = false;
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (start === -1 && ch === '{') { start = i; }
    if (start === -1) continue;
    if (esc)         { esc = false; continue; }
    if (ch === '\\') { esc = true;  continue; }
    if (ch === '"' && !esc) { inStr = !inStr; continue; }
    if (!inStr) {
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) return str.slice(start, i + 1);
      }
    }
  }
  return null;
}

// stdout에서 마지막 완전한 JSON 객체 추출 (진행 출력 이후 최종 결과용)
// stdout에서 마지막 완전한 JSON 객체 추출
// Python 스크립트는 마지막 줄에 JSON을 출력하므로 역순으로 탐색
function extractLastJson(str, requiredKey = null) {
  // 줄 단위로 역순 탐색
  const lines = str.split('\n');
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line.startsWith('{') || line.length < 100) continue;
    try {
      const parsed = JSON.parse(line);
      if (requiredKey && parsed[requiredKey] === undefined) continue;
      return line;
    } catch(_) {}
  }
  // 줄 단위 실패 시 전체에서 가장 긴 JSON 탐색
  let bestJson = null, bestLen = 100;
  let i = 0;
  while (i < str.length) {
    const s = str.indexOf('{', i);
    if (s === -1) break;
    let depth = 0, inStr = false, esc = false, j = s;
    for (; j < str.length; j++) {
      const ch = str[j];
      if (esc)         { esc = false; continue; }
      if (ch === '\\') { esc = true;  continue; }
      if (ch === '"' && !esc) { inStr = !inStr; continue; }
      if (!inStr) {
        if (ch === '{') depth++;
        else if (ch === '}') { depth--; if (depth === 0) break; }
      }
    }
    if (depth === 0) {
      const candidate = str.slice(s, j+1);
      if (candidate.length > bestLen) {
        try {
          const parsed = JSON.parse(candidate);
          if (!requiredKey || parsed[requiredKey] !== undefined) {
            bestJson = candidate;
            bestLen  = candidate.length;
          }
        } catch(_) {}
      }
    }
    i = s + 1;
  }
  return bestJson;
}

// ── Python 스크립트 실행 헬퍼 ─────────────────────────────────
function runPython(scriptPath, txtPath, geminiKey) {
  return new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      GEMINI_API_KEY:   geminiKey || process.env.GEMINI_API_KEY || '',
      GCP_API_KEY:      geminiKey || process.env.GCP_API_KEY    || '',
      GOOGLE_API_KEY:   geminiKey || process.env.GOOGLE_API_KEY  || '',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8:       '1',
    };

    const scriptName  = path.basename(scriptPath);
    const pythonCmd   = process.platform === 'win32' ? 'python' : 'python3';
    const fallbackCmd = pythonCmd === 'python' ? 'python3' : 'python';

    function trySpawn(cmd, onFail) {
      const proc = spawn(cmd, ['-u', scriptPath, txtPath], { env });
      let stdout = '', stderr = '';

      proc.stdout.on('data', d => { stdout += d.toString('utf8'); });
      proc.stderr.on('data', d => { stderr += d.toString('utf8'); });

      const timer = setTimeout(() => {
        proc.kill();
        reject(new Error(`${scriptName} 타임아웃 (180초)`));
      }, 180000);

      proc.on('close', code => {
        clearTimeout(timer);
        if (stderr) console.error(`[${scriptName}] stderr:`, stderr.slice(0, 300));
        if (code !== 0) {
          if (onFail) return onFail();
          return reject(new Error(`${scriptName} 실패 (exit ${code}): ${stderr.slice(0, 200)}`));
        }
        const jsonStr = extractLastJson(stdout) || extractFirstJson(stdout);
        if (!jsonStr) {
          return reject(new Error(`${scriptName} JSON 없음: ${stdout.slice(-200)}`));
        }
        try {
          resolve(JSON.parse(jsonStr));
        } catch (e) {
          reject(new Error(`${scriptName} JSON 파싱 오류: ${jsonStr.slice(0, 200)}`));
        }
      });

      proc.on('error', err => {
        clearTimeout(timer);
        if (onFail) return onFail();
        reject(new Error(`Python 실행 불가: ${err.message}`));
      });
    }

    trySpawn(pythonCmd, () => trySpawn(fallbackCmd, null));
  });
}

// ── 파일명에서 날짜/course_id 파싱 ───────────────────────────
function parseFileMeta(filename) {
  const stem  = filename.replace(/\.txt$/, '');
  const match = stem.match(/^(\d{4}-\d{2}-\d{2})_(.+)$/);
  return match
    ? { date: match[1], course_id: match[2] }
    : { date: '',       course_id: stem };
}

// ── 라우트: 로그인 ────────────────────────────────────────────
app.get('/', (req, res) => res.sendFile(path.join(__dirname, 'public', 'login.html')));

app.post('/login', (req, res) => {
  const { username, password } = req.body;
  if (username === 'admin' && password === 'admin') {
    req.session.user = username;
    return res.redirect('/dashboard');
  }
  res.redirect('/?error=1');
});

// 기존 dashboard → analysis로 변경 (하위 호환 리다이렉트 포함)
app.get('/dashboard', requireAuth, (req, res) => res.redirect('/instructors'));
// 업로드/분석 페이지
app.get('/upload', requireAuth, (req, res) =>
  res.sendFile(path.join(__dirname, 'public', 'dashboard.html'))
);
app.get('/instructors', requireAuth, (req, res) =>
  res.sendFile(path.join(__dirname, 'public', 'instructors.html'))
);
app.get('/instructor', requireAuth, (req, res) =>
  res.sendFile(path.join(__dirname, 'public', 'instructor.html'))
);
app.get('/analysis', requireAuth, (req, res) =>
  res.sendFile(path.join(__dirname, 'public', 'analysis.html'))
);

app.get('/logout', (req, res) => req.session.destroy(() => res.redirect('/')));

// ── 라우트: 분석 API ──────────────────────────────────────────
app.post('/api/analyze', requireAuth, upload.single('file'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: '파일이 필요합니다.' });

  const txtPath   = req.file.path;
  const origName  = req.file.originalname;
  const geminiKey = (
    req.body.gemini_key ||
    process.env.GCP_API_KEY ||
    process.env.GEMINI_API_KEY ||
    process.env.GOOGLE_API_KEY ||
    ''
  );
  const timestamp = new Date();
  const fileMeta  = parseFileMeta(origName);
  const _cancelKey = `${fileMeta.date}|${fileMeta.course_id}`;
  let _cancelled = false;
  activeAnalyses.set(_cancelKey, { abort: () => { _cancelled = true; } });

  // SSE 스트리밍
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  const send = (data) => res.write(`data: ${JSON.stringify(data)}\n\n`);

  const allResults = {};

  for (let i = 0; i < CATE_SCRIPTS.length; i++) {
    const { key, script, label } = CATE_SCRIPTS[i];
    send({ type: 'progress', step: i + 1, total: CATE_SCRIPTS.length, label });

    if (!fs.existsSync(script)) {
      const msg = `스크립트 없음: ${script}`;
      console.error(`[${key}] ${msg}`);
      send({ type: 'error', step: i + 1, label, message: msg });
      allResults[key] = { error: msg };
      continue;
    }

    try {
      const result = await runPython(script, txtPath, geminiKey);
      const items  = result.items || (Object.values(result)[0]) || result;
      allResults[key] = { items };
    } catch (err) {
      console.error(`[${key}] 오류:`, err.message);
      send({ type: 'error', step: i + 1, label, message: err.message });
      allResults[key] = { error: err.message };
    }
  }

  // 업로드 임시 파일 삭제
  try { fs.unlinkSync(txtPath); } catch (_) {}

  // ── 메타데이터 매핑으로 강의자 자동 설정 ──────────────────
  const meta = lookupMeta(fileMeta.date, fileMeta.course_id);
  const instructor = meta?.instructor || '';
  if (instructor) console.log(`✅ 강의자 매핑: ${instructor} (${fileMeta.date} / ${fileMeta.course_id})`);
  else            console.log(`ℹ️  강의자 매핑 실패 (date=${fileMeta.date}, course_id=${fileMeta.course_id})`);

  // ── 카테고리별 MongoDB 저장 ────────────────────────────────
  const savedIds = {};
  for (const [cateKey, cateVal] of Object.entries(allResults)) {
    try {
      const doc = await CategoryResult.findOneAndUpdate(
        { date: fileMeta.date, course_id: fileMeta.course_id, category: cateKey },
        {
          timestamp,
          filename:   origName,
          date:       fileMeta.date,
          course_id:  fileMeta.course_id,
          instructor,
          category:   cateKey,
          items:      cateVal.items || cateVal,
          error:      cateVal.error || '',
        },
        { upsert: true, new: true }
      );
      savedIds[cateKey] = doc._id.toString();
      console.log(`✅ MongoDB 저장: ${cateKey} → ${doc._id} (${origName})`);
    } catch (dbErr) {
      console.error(`❌ MongoDB 저장 실패 (${cateKey}):`, dbErr.message);
    }
  }

  const finalData = {
    ids:        savedIds,
    timestamp:  timestamp.toISOString(),
    filename:   origName,
    date:       fileMeta.date,
    course_id:  fileMeta.course_id,
    instructor,
    categories: allResults,
  };

  activeAnalyses.delete(_cancelKey);
  if (_cancelled) {
    send({ type: 'cancelled' });
  } else {
    send({ type: 'done', data: finalData });
  }
  res.end();
});

// ── 라우트: 일괄 분석 (여러 파일) ───────────────────────────
app.post('/api/analyze/bulk', requireAuth, upload.array('files', 50), async (req, res) => {
  if (!req.files || !req.files.length) return res.status(400).json({ error: '파일이 필요합니다.' });

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  const send = (data) => res.write(`data: ${JSON.stringify(data)}\n\n`);

  const geminiKey = req.body.gemini_key || process.env.GCP_API_KEY || process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || '';
  const total = req.files.length;

  send({ type: 'bulk_start', total });

  for (let fi = 0; fi < total; fi++) {
    const file = req.files[fi];
    const txtPath  = file.path;
    const origName = file.originalname;
    const fileMeta = parseFileMeta(origName);

    send({ type: 'file_start', index: fi + 1, total, filename: origName });

    const allResults = {};
    for (let i = 0; i < CATE_SCRIPTS.length; i++) {
      const { key, script, label } = CATE_SCRIPTS[i];
      send({ type: 'progress', fileIndex: fi + 1, step: i + 1, total: CATE_SCRIPTS.length, label, filename: origName });
      if (!fs.existsSync(script)) { allResults[key] = { error: `스크립트 없음: ${script}` }; continue; }
      try {
        const result = await runPython(script, txtPath, geminiKey);
        allResults[key] = { items: result.items || Object.values(result)[0] || result };
      } catch (err) {
        allResults[key] = { error: err.message };
      }
    }

    try { fs.unlinkSync(txtPath); } catch (_) {}

    const meta       = lookupMeta(fileMeta.date, fileMeta.course_id);
    const instructor = meta?.instructor || '';
    const timestamp  = new Date();

    for (const [cateKey, cateVal] of Object.entries(allResults)) {
      try {
        await CategoryResult.findOneAndUpdate(
          { date: fileMeta.date, course_id: fileMeta.course_id, category: cateKey },
          { timestamp, filename: origName, date: fileMeta.date, course_id: fileMeta.course_id, instructor, category: cateKey, items: cateVal.items || cateVal, error: cateVal.error || '' },
          { upsert: true, new: true }
        );
      } catch (dbErr) { console.error(`❌ MongoDB 저장 실패 (${cateKey}):`, dbErr.message); }
    }

    send({ type: 'file_done', index: fi + 1, total, filename: origName, instructor, date: fileMeta.date, course_id: fileMeta.course_id });
  }

  send({ type: 'bulk_done', total });
  res.end();
});

// ── 라우트: 전체 평균 벤치마크 API ──────────────────────────
app.get('/api/benchmark', requireAuth, async (req, res) => {
  try {
    const docs = await CategoryResult.find({}, { category: 1, items: 1 }).lean();
    const sums = {}, cnts = {};
    const ITEM_CATE = {
      '1.1':'cate1','1.2':'cate1','1.3':'cate1',
      '2.1':'cate2','2.2':'cate2','2.3':'cate2','2.4':'cate2','2.5':'cate2',
      '3.1':'cate3','3.2':'cate3','3.3':'cate3','3.4':'cate3',
      '4.1':'cate4','4.2':'cate4','4.3':'cate4',
      '5.1':'cate5','5.2':'cate5','5.3':'cate5',
    };
    docs.forEach(doc => {
      const ck = doc.category;
      if (!sums[ck]) { sums[ck] = 0; cnts[ck] = 0; }
      const items = doc.items || {};
      const vals = Object.values(items).map(v => parseFloat(v?.score ?? null)).filter(v => !isNaN(v));
      if (vals.length) { sums[ck] += vals.reduce((a, b) => a + b, 0) / vals.length; cnts[ck]++; }
    });
    const benchmark = {};
    for (const ck of Object.keys(sums)) {
      benchmark[ck] = cnts[ck] ? Math.round((sums[ck] / cnts[ck]) * 100 / 5) : 0;
    }
    res.json(benchmark);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 강사 등급 목록 ───────────────────────────────────
app.get('/api/instructor-grades', requireAuth, async (req, res) => {
  try {
    const docs = await InstructorSummary.find({}, { instructor: 1, proficiency_grade: 1 }).lean();
    res.json(docs);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 강사 목록 API ────────────────────────────────────
// 강사별 강의 수, 최근 분석일, 평균 점수 반환
app.get('/api/instructors', requireAuth, async (req, res) => {
  try {
    const docs = await CategoryResult
      .find({}, { instructor: 1, course_id: 1, date: 1, timestamp: 1, items: 1, category: 1 })
      .sort({ timestamp: -1 })
      .lean();

    // 강사별 그룹핑
    const map = new Map();
    docs.forEach(d => {
      const name = d.instructor || '미확인';
      if (!map.has(name)) {
        map.set(name, { instructor: name, lectures: new Set(), lastDate: '', dates: [] });
      }
      const entry = map.get(name);
      const key = `${d.date}|${d.course_id}`;
      entry.lectures.add(key);
      if (!entry.lastDate || d.date > entry.lastDate) entry.lastDate = d.date;
    });

    const result = [...map.entries()].map(([name, v]) => ({
      instructor:    name,
      lecture_count: v.lectures.size,
      last_date:     v.lastDate,
      courses: [...v.lectures].map(k => k.split('|')[1]),
    }));

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 강사 강의 목록 API ───────────────────────────────
app.get('/api/instructor/:name/lectures', requireAuth, async (req, res) => {
  try {
    const instructor = decodeURIComponent(req.params.name);
    const docs = await CategoryResult
      .find({ instructor }, { course_id: 1, date: 1, timestamp: 1, category: 1, items: 1 })
      .sort({ date: -1 })
      .lean();

    const grouped = new Map();
    docs.forEach(d => {
      const key = `${d.date}|${d.course_id}`;
      if (!grouped.has(key)) {
        grouped.set(key, {
          resultFile: key, date: d.date, course_id: d.course_id,
          instructor, timestamp: d.timestamp, categories: {}
        });
      }
      grouped.get(key).categories[d.category] = { items: d.items };
    });

    res.json([...grouped.values()]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 강사 종합평가 조회 (캐시 우선) ───────────────────
// ── 실행 중인 summary 프로세스 추적 ─────────────────────────
const _summaryProcs = new Map(); // instructor → child process

app.get('/api/instructor/:name/summary', requireAuth, async (req, res) => {
  try {
    const instructor = decodeURIComponent(req.params.name);
    const { course_id, refresh } = req.query;

    // 캐시된 결과 조회 (refresh=1이면 재생성)
    if (refresh !== '1') {
      const filter = { instructor };
      if (course_id) filter.course_id = course_id;
      const cached = await InstructorSummary.findOne(filter).sort({ generated_at: -1 }).lean();
      if (cached) return res.json({ ...cached, _cached: true });
      // 캐시 없고 refresh 요청 아니면 404 반환 (자동 생성 방지)
      return res.status(404).json({ error: '종합평가 없음. 생성 버튼을 눌러주세요.' });
    }

    // instructor_summary.py 실행 (refresh=1 요청 시만)
    const scriptPath = path.join(__dirname, 'instructor_summary.py');
    if (!fs.existsSync(scriptPath)) {
      return res.status(404).json({ error: 'instructor_summary.py 없음 — 프로젝트 루트에 파일을 놓으세요.' });
    }

    const geminiKey = req.headers['x-gemini-key'] || process.env.GEMINI_API_KEY || '';
    const env = {
      ...process.env,
      GEMINI_API_KEY:   geminiKey,
      GCP_API_KEY:      geminiKey,
      GOOGLE_API_KEY:   geminiKey,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8:       '1',
    };

    const args = ['-u', scriptPath, '--instructor', instructor];
    if (course_id) args.push('--course', course_id);

    const result = await new Promise((resolve, reject) => {
      const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
      const proc = spawn(pythonCmd, args, { env });
      _summaryProcs.set(instructor, proc);
      let stdout = '', stderr = '', cancelled = false;
      proc.stdout.on('data', d => { stdout += d.toString('utf8'); });
      proc.stderr.on('data', d => { stderr += d.toString('utf8'); });
      const timer = setTimeout(() => { proc.kill(); reject(new Error('타임아웃 (300초)')); }, 300000);
      proc.on('close', code => {
        clearTimeout(timer);
        _summaryProcs.delete(instructor);
        if (cancelled) return reject(Object.assign(new Error('cancelled'), { cancelled: true }));
        if (code !== 0) return reject(new Error(stderr.slice(0, 300)));
        const jsonStr = extractLastJson(stdout,'date') || extractLastJson(stdout) || extractFirstJson(stdout);
        if (!jsonStr) return reject(new Error('JSON 없음: ' + stdout.slice(-200)));
        try { resolve(JSON.parse(jsonStr)); } catch(e) { reject(e); }
      });
      proc.on('error', err => { clearTimeout(timer); _summaryProcs.delete(instructor); reject(err); });
      // 취소 플래그 설정용
      proc._setCancelled = () => { cancelled = true; };
    });

    // MongoDB 저장 (upsert)
    const filter = { instructor: result.instructor, course_id: result.course_id || '' };
    await InstructorSummary.findOneAndUpdate(filter, {
      ...result, generated_at: new Date()
    }, { upsert: true, new: true });

    res.json(result);
  } catch (err) {
    if (err.cancelled) return res.status(499).json({ error: '취소됨' });
    console.error('/api/instructor/summary 오류:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 강사 종합평가 저장된 결과 직접 저장 (Python 외부 호출용) ──
app.post('/api/instructor/:name/summary/cancel', requireAuth, (req, res) => {
  const instructor = decodeURIComponent(req.params.name);
  const proc = _summaryProcs.get(instructor);
  if (proc) {
    if (proc._setCancelled) proc._setCancelled();
    proc.kill();
    _summaryProcs.delete(instructor);
    console.log(`⛔ 종합평가 생성 취소: ${instructor}`);
    res.json({ ok: true });
  } else {
    res.json({ ok: false, message: '실행 중인 프로세스 없음' });
  }
});

app.post('/api/instructor/:name/summary', requireAuth, async (req, res) => {
  try {
    const instructor = decodeURIComponent(req.params.name);
    const data = req.body;
    const filter = { instructor, course_id: data.course_id || '' };
    const doc = await InstructorSummary.findOneAndUpdate(filter, {
      ...data, instructor, generated_at: new Date()
    }, { upsert: true, new: true });
    res.json({ ok: true, _id: doc._id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 일별 요약 조회 (캐시 우선) ──────────────────────
app.get('/api/daily-summary/:key', requireAuth, async (req, res) => {
  try {
    const keyStr  = decodeURIComponent(req.params.key);
    const [date, course_id] = keyStr.split('|');
    if (!date || !course_id) return res.status(400).json({ error: '잘못된 키 (date|course_id)' });
    const { refresh } = req.query;

    // 캐시 조회
    if (refresh !== '1') {
      const cached = await DailySummary.findOne({ date, course_id }).lean();
      if (cached) return res.json({ ...cached, _cached: true });
    }

    // daily_summary.py 실행
    const scriptPath = path.join(__dirname, 'daily_summary.py');
    if (!fs.existsSync(scriptPath)) {
      return res.status(404).json({ error: 'daily_summary.py 없음 — 프로젝트 루트에 파일을 놓으세요.' });
    }

    // 메타에서 instructor 조회
    const metaDoc = await CategoryResult.findOne({ date, course_id }, { instructor: 1 }).lean();
    const instructor = metaDoc?.instructor || '';

    const geminiKey = req.headers['x-gemini-key'] || process.env.GCP_API_KEY || process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || '';
    const env = {
      ...process.env,
      GEMINI_API_KEY: geminiKey, GCP_API_KEY: geminiKey, GOOGLE_API_KEY: geminiKey,
      PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1',
    };

    const args = ['-u', scriptPath, '--date', date, '--course', course_id];
    if (instructor) args.push('--instructor', instructor);

    const result = await new Promise((resolve, reject) => {
      const cmd  = process.platform === 'win32' ? 'python' : 'python3';
      const proc = spawn(cmd, args, { env });
      let stdout = '', stderr = '';
      proc.stdout.on('data', d => { stdout += d.toString('utf8'); });
      proc.stderr.on('data', d => { stderr += d.toString('utf8'); });
      const timer = setTimeout(() => { proc.kill(); reject(new Error('타임아웃 (180초)')); }, 180000);
      proc.on('close', code => {
        clearTimeout(timer);
        if (code !== 0) return reject(new Error(stderr.slice(0, 300)));
        const jsonStr = extractLastJson(stdout,'date') || extractLastJson(stdout) || extractFirstJson(stdout);
        if (!jsonStr) return reject(new Error('JSON 없음: ' + stdout.slice(-200)));
        try { resolve(JSON.parse(jsonStr)); } catch(e) { reject(e); }
      });
      proc.on('error', err => { clearTimeout(timer); reject(err); });
    });

    // MongoDB upsert
    await DailySummary.findOneAndUpdate(
      { date, course_id },
      { ...result, generated_at: new Date() },
      { upsert: true, new: true }
    );

    res.json(result);
  } catch (err) {
    console.error('/api/daily-summary 오류:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 일별 요약 직접 저장 (Python 외부 호출용) ─────────
app.post('/api/daily-summary', requireAuth, async (req, res) => {
  try {
    const data = req.body;
    const filter = { date: data.date, course_id: data.course_id };
    const doc = await DailySummary.findOneAndUpdate(filter,
      { ...data, generated_at: new Date() },
      { upsert: true, new: true }
    );
    res.json({ ok: true, _id: doc._id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: DOCX 생성 ────────────────────────────────────────
app.post('/api/export/docx', requireAuth, async (req, res) => {
  try {
    const tmpJson = path.join(UPLOAD_DIR, `docx_${Date.now()}.json`);
    const tmpDocx = path.join(UPLOAD_DIR, `docx_${Date.now()}.docx`);
    fs.writeFileSync(tmpJson, JSON.stringify(req.body), 'utf8');

    const scriptPath = path.join(__dirname, 'generate_docx.py');
    const cmd = process.platform === 'win32' ? 'python' : 'python3';

    await new Promise((resolve, reject) => {
      const proc = spawn(cmd, [scriptPath, tmpJson, tmpDocx], {
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
      });
      let stderr = '';
      proc.stderr.on('data', d => { stderr += d.toString(); });
      proc.on('close', code => {
        if (code !== 0) reject(new Error(stderr));
        else resolve();
      });
    });

    const docxName = req.body.filename || 'report.docx';
    res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    res.setHeader('Content-Disposition', `attachment; filename*=UTF-8''${encodeURIComponent(docxName)}`);
    res.sendFile(tmpDocx, {}, () => {
      try { fs.unlinkSync(tmpJson); fs.unlinkSync(tmpDocx); } catch(_) {}
    });
  } catch (err) {
    console.error('DOCX 생성 오류:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 분석 취소 ────────────────────────────────────────
// 진행 중인 분석을 취소하고 부분 저장된 데이터 삭제
const activeAnalyses = new Map(); // key: date|course_id → abortController

app.post('/api/analyze/cancel', requireAuth, async (req, res) => {
  try {
    const { date, course_id } = req.body;
    if (!date || !course_id) return res.status(400).json({ error: '키 없음' });
    const key = `${date}|${course_id}`;

    // 진행 중인 프로세스 종료
    const ctrl = activeAnalyses.get(key);
    if (ctrl) { ctrl.abort(); activeAnalyses.delete(key); }

    // 부분 저장된 데이터 삭제
    const r = await CategoryResult.deleteMany({ date, course_id });
    console.log(`🚫 분석 취소: ${key} (${r.deletedCount}개 삭제)`);
    res.json({ ok: true, deleted: r.deletedCount });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 이력 조회 ────────────────────────────────────────
// 강의 파일 단위로 묶어서 반환 (date+course_id 기준 dedup)
app.get('/api/history', requireAuth, async (req, res) => {
  try {
    const docs = await CategoryResult
      .find({}, { filename: 1, timestamp: 1, date: 1, course_id: 1, instructor: 1, category: 1 })
      .sort({ timestamp: -1 })
      .lean();

    // date+course_id 기준으로 묶어 강의 단위 이력 생성
    const seen = new Map();
    docs.forEach(d => {
      const key = `${d.date}|${d.course_id}`;
      if (!seen.has(key)) {
        seen.set(key, {
          key,
          filename:   d.filename,
          date:       d.date,
          course_id:  d.course_id,
          instructor: d.instructor,
          timestamp:  d.timestamp,
          resultFile: key,   // 조회 키로 사용
        });
      }
    });

    res.json([...seen.values()].slice(0, 20));
  } catch (err) {
    console.error('/api/history 오류:', err.message);
    res.status(500).json({ error: 'DB 조회 오류' });
  }
});

// ── 라우트: 결과 단건 조회 (date|course_id 키로 전체 카테고리 반환) ──
app.get('/api/result/:key', requireAuth, async (req, res) => {
  try {
    const keyStr = decodeURIComponent(req.params.key);
    const [date, course_id] = keyStr.split('|');
    if (!date || !course_id) return res.status(400).json({ error: '잘못된 키 형식 (date|course_id)' });

    const docs = await CategoryResult.find({ date, course_id }).lean();
    if (!docs.length) return res.status(404).json({ error: '결과 없음' });

    // categories 구조로 재조합
    const base = docs[0];
    const categories = {};
    docs.forEach(d => { categories[d.category] = { items: d.items, error: d.error }; });

    res.json({
      filename:   base.filename,
      date:       base.date,
      course_id:  base.course_id,
      instructor: base.instructor,
      timestamp:  base.timestamp,
      categories,
    });
  } catch (err) {
    console.error('/api/result 오류:', err.message);
    res.status(500).json({ error: 'DB 조회 오류' });
  }
});

// ── 라우트: 결과 삭제 ────────────────────────────────────────
app.delete('/api/result/:key', requireAuth, async (req, res) => {
  try {
    const keyStr = decodeURIComponent(req.params.key);
    const [date, course_id] = keyStr.split('|');
    if (!date || !course_id) return res.status(400).json({ error: '잘못된 키 형식' });

    const r = await CategoryResult.deleteMany({ date, course_id });
    await DailySummary.deleteMany({ date, course_id });

    // 해당 date|course_id의 강사명을 categoryresults에서 먼저 찾아둠 (삭제 전에 이미 지워졌으므로 못 찾을 수 있음)
    // 대신 instructorsummaries에서 강의가 없는 강사를 정리
    const activeInstructors = await CategoryResult.distinct('instructor');
    const activeSet = new Set(activeInstructors.filter(Boolean));
    const orphans = await InstructorSummary.deleteMany({
      instructor: { $nin: [...activeSet] }
    });
    if (orphans.deletedCount > 0) {
      console.log(`🗑️ 고아 InstructorSummary ${orphans.deletedCount}개 자동 삭제`);
    }

    console.log(`🗑️ 삭제 완료: ${keyStr} (${r.deletedCount}개 카테고리)`);
    res.json({ ok: true, deleted: r.deletedCount });
  } catch (err) {
    console.error('/api/result DELETE 오류:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 고아 InstructorSummary 정리 ─────────────────────
// categoryresults에 없는 강사의 summary를 삭제
app.delete('/api/cleanup/orphan-summaries', requireAuth, async (req, res) => {
  try {
    const activeDocs = await CategoryResult.distinct('instructor');
    const activeSet  = new Set(activeDocs.filter(Boolean));
    const result     = await InstructorSummary.deleteMany({
      instructor: { $nin: [...activeSet] }
    });
    console.log(`🗑️ 고아 InstructorSummary ${result.deletedCount}개 삭제`);
    res.json({ ok: true, deleted: result.deletedCount });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── 라우트: 필터 조회 ────────────────────────────────────────
app.get('/api/results', requireAuth, async (req, res) => {
  try {
    const { date, course_id, instructor, limit = 100, skip = 0 } = req.query;
    const filter = {};
    if (date)       filter.date       = date;
    if (course_id)  filter.course_id  = course_id;
    if (instructor) filter.instructor = instructor;

    const docs = await CategoryResult.find(filter)
      .sort({ timestamp: -1 })
      .skip(Number(skip))
      .limit(Number(limit))
      .lean();

    // date+course_id 단위로 그룹핑해서 반환
    const grouped = new Map();
    docs.forEach(d => {
      const key = `${d.date}|${d.course_id}`;
      if (!grouped.has(key)) {
        grouped.set(key, {
          filename: d.filename, date: d.date, course_id: d.course_id,
          instructor: d.instructor, timestamp: d.timestamp, categories: {}
        });
      }
      grouped.get(key).categories[d.category] = { items: d.items, error: d.error };
    });

    res.json([...grouped.values()]);
  } catch (err) {
    res.status(500).json({ error: 'DB 조회 오류' });
  }
});

// ── CSV 업로드용 multer (별도 인스턴스) ──────────────────────
const csvUpload = multer({
  dest: UPLOAD_DIR,
  fileFilter: (req, file, cb) => {
    if (file.originalname.endsWith('.csv') || file.mimetype === 'text/csv'
        || file.mimetype === 'application/vnd.ms-excel') cb(null, true);
    else cb(new Error('.csv 파일만 업로드 가능합니다.'));
  },
  limits: { fileSize: 5 * 1024 * 1024 },
});

// ── 라우트: 메타데이터 CSV 업로드 ────────────────────────────
app.post('/api/meta/upload', requireAuth, csvUpload.single('csv'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'CSV 파일이 필요합니다.' });
  try {
    await loadMetaCSV(req.file.path);
    fs.unlinkSync(req.file.path);
    res.json({ ok: true, count: Object.keys(metaCache).length });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── 라우트: 메타데이터 상태 조회 (인증 불필요 — 상태만 반환) ──
app.get('/api/meta/status', async (req, res) => {
  const cacheCount = Object.keys(metaCache).length;
  let dbCount = 0;
  try { dbCount = await Meta.countDocuments(); } catch(_) {}
  res.json({ loaded: cacheCount > 0, count: cacheCount, db_count: dbCount });
});

// ── python-docx 자동 설치 확인 ───────────────────────────────
function ensurePythonDocx() {
  return new Promise((resolve) => {
    const cmd = process.platform === 'win32' ? 'python' : 'python3';
    const check = spawn(cmd, ['-c', 'import docx; import PIL'], { stdio: 'pipe' });
    check.on('close', code => {
      if (code === 0) {
        console.log('✅ python-docx / Pillow 설치 확인됨');
        return resolve();
      }
      console.log('⏳ 패키지 없음 — pip으로 설치 중...');
      const pip = process.platform === 'win32' ? 'pip' : 'pip3';
      const install = spawn(pip, ['install', 'python-docx', 'Pillow'], { stdio: 'inherit' });
      install.on('close', c => {
        if (c === 0) console.log('✅ python-docx / Pillow 설치 완료');
        else console.error('❌ 설치 실패 — 수동으로 실행하세요: pip install python-docx Pillow');
        resolve();
      });
    });
  });
}

app.listen(PORT, async () => {
  console.log(`✅ 서버 실행: http://localhost:${PORT}`);

  // python-docx 설치 확인
  await ensurePythonDocx();

  // 1. DB에 저장된 메타데이터 먼저 캐시 복원
  try {
    const count = await refreshMetaCache();
    if (count > 0) {
      console.log(`✅ MongoDB에서 메타데이터 ${count}개 복원`);
    }
  } catch (e) {
    console.error('메타데이터 캐시 복원 실패:', e.message);
  }

  // 2. 프로젝트 루트에 CSV가 있으면 추가 로드 (DB에 없는 항목 보완)
  const defaultCSV = path.join(__dirname, '강의_메타데이터.csv');
  if (fs.existsSync(defaultCSV)) {
    await loadMetaCSV(defaultCSV);
  } else if (Object.keys(metaCache).length === 0) {
    console.log('ℹ️  강의_메타데이터.csv 없음 — 대시보드에서 업로드하세요.');
  }
});