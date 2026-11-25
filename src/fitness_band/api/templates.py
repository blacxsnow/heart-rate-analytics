"""Single-page acquisition dashboard (no external JS/CSS dependencies)."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Band 9 Acquisition</title>
<style>
  :root {
    --bg:#11161d; --panel:#1a222c; --panel2:#222c38; --text:#e7edf5;
    --muted:#8fa0b3; --accent:#ff7a45; --ok:#46d39a; --warn:#f2c14e;
    --bad:#ff5d5d; --line:#ff7a45; --grid:#2b3745;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:18px 22px; border-bottom:1px solid #263241; display:flex;
           align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
  h1 { font-size:20px; margin:0; font-weight:650; letter-spacing:.2px; }
  .muted { color:var(--muted); }
  main { padding:18px 22px 40px; max-width:1500px; margin:0 auto; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(165px,1fr));
           gap:12px; margin-bottom:16px; }
  .card { background:var(--panel); border:1px solid #263241; border-radius:12px; padding:12px 14px; }
  .card .label { color:var(--muted); font-size:12px; text-transform:uppercase;
                 letter-spacing:.5px; }
  .card .value { font-size:22px; font-weight:650; margin-top:4px; }
  .card .sub { color:var(--muted); font-size:12px; margin-top:2px; }
  .pill { display:inline-block; padding:2px 9px; border-radius:999px;
          font-size:12px; font-weight:600; background:#2b3745; }
  .pill.connected, .pill.running { background:#123b2e; color:var(--ok); }
  .pill.disconnected, .pill.stopped { background:#3a2020; color:var(--bad); }
  .pill.scanning, .pill.starting { background:#3a321c; color:var(--warn); }
  .pill.paused { background:#2d2d3a; color:var(--muted); }
  .panel { background:var(--panel); border:1px solid #263241; border-radius:12px;
           padding:14px; margin-bottom:16px; }
  .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .row.between { justify-content:space-between; }
  button { background:var(--panel2); color:var(--text); border:1px solid #334252;
           border-radius:9px; padding:8px 12px; cursor:pointer; font-weight:600; }
  button:hover { border-color:var(--accent); }
  button.primary { background:var(--accent); color:#1b1009; border-color:var(--accent); }
  button.danger { border-color:#6a3030; color:#ffb3b3; }
  button.active { outline:2px solid var(--accent); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  svg { width:100%; height:auto; display:block; background:#0d1218;
        border-radius:10px; border:1px solid #263241; }
  .grid-line { stroke:var(--grid); stroke-width:1; }
  .grid-text { fill:var(--muted); font-size:11px; }
  .hr-line { fill:none; stroke:var(--line); stroke-width:2; stroke-linejoin:round; }
  .gap-band { fill:rgba(255,93,93,.13); }
  .gap-edge { stroke:rgba(255,93,93,.6); stroke-width:1; stroke-dasharray:4 3; }
  .legend { display:flex; gap:16px; color:var(--muted); font-size:12px;
            margin-top:8px; flex-wrap:wrap; }
  .legend span::before { content:""; display:inline-block; width:10px; height:10px;
                         border-radius:2px; margin-right:6px; vertical-align:-1px; }
  .legend .hr::before { background:var(--line); }
  .legend .gap::before { background:rgba(255,93,93,.5); }
  form { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
         gap:10px; align-items:end; }
  label { color:var(--muted); font-size:12px; display:block; margin-bottom:4px; }
  input, textarea { width:100%; background:#0f151c; color:var(--text);
                    border:1px solid #334252; border-radius:8px; padding:8px 10px;
                    font:inherit; }
  textarea { min-height:38px; resize:vertical; }
  .ann { display:flex; justify-content:space-between; gap:12px; padding:10px 0;
         border-bottom:1px solid #263241; }
  .ann:last-child { border-bottom:0; }
  .ann .when { font-weight:600; }
  .ann .notes { color:var(--muted); font-size:12px; }
  @media (max-width:640px) { .card .value { font-size:18px; } main { padding:12px; } }
</style>
</head>
<body>
<header>
  <div>
    <h1>Huawei Band 9 · Acquisition</h1>
    <div class="muted" id="service-line">service starting…</div>
    <div class="muted" style="font-size:12px">All timestamps: Asia/Kolkata (IST, UTC+05:30)</div>
  </div>
  <div class="row">
    <span class="muted" id="clock">— IST</span>
    <button id="export">Export CSV</button>
    <button id="restart" class="danger">Restart service</button>
  </div>
</header>
<main>
  <div class="muted" id="hint" style="margin:-4px 0 12px"></div>
  <section class="cards">
    <div class="card"><div class="label">Connection</div><div class="value"><span class="pill" id="conn">unknown</span></div><div class="sub" id="adapter">adapter —</div></div>
    <div class="card"><div class="label">Current HR</div><div class="value" id="hr">—</div><div class="sub" id="hr-at">no data</div></div>
    <div class="card"><div class="label">Sampling</div><div class="value" id="rate">—</div><div class="sub">seconds between packets</div></div>
    <div class="card"><div class="label">Session</div><div class="value" id="session">—</div><div class="sub" id="session-id">session —</div></div>
    <div class="card"><div class="label">Measurements</div><div class="value" id="total">0</div><div class="sub" id="db-size">database —</div></div>
    <div class="card"><div class="label">Last connection</div><div class="value" id="last-conn" style="font-size:15px">—</div><div class="sub" id="last-disc">last disconnect —</div></div>
    <div class="card"><div class="label">Reconnects</div><div class="value" id="reconnects">0</div><div class="sub" id="spool">spool 0</div></div>
    <div class="card"><div class="label">Band battery</div><div class="value" id="battery-value">—</div><div class="sub" id="battery-at">manual; no BLE service</div></div>
  </section>

  <section class="panel">
    <div class="row between" style="margin-bottom:10px">
      <div class="row">
        <strong>Heart rate</strong>
        <span class="muted" id="window-label">last 5 minutes</span>
      </div>
      <div class="row" id="windows">
        <button data-window="1">1 min</button>
        <button data-window="5" class="active">5 min</button>
        <button data-window="15">15 min</button>
        <button data-window="60">1 hour</button>
      </div>
    </div>
    <svg id="chart" viewBox="0 0 1000 320" preserveAspectRatio="none" role="img" aria-label="Heart rate graph">
      <g id="bands"></g>
      <g id="grid"></g>
      <path id="line" class="hr-line" d=""></path>
      <g id="last-dot"></g>
    </svg>
    <div class="legend"><span class="hr">HR sample</span><span class="gap">missing / disconnected</span></div>
  </section>

  <section class="panel">
    <div class="row between" style="margin-bottom:10px">
      <strong>Acquisition control</strong>
      <span class="muted">The daemon keeps running when this page is closed.</span>
    </div>
    <div class="row">
      <button data-action="start" class="primary">Start acquisition</button>
      <button data-action="connect">Connect</button>
      <button data-action="disconnect">Disconnect</button>
      <button data-action="stop">Stop acquisition</button>
      <button data-action="reconnect">Reconnect now</button>
      <button data-action="reset_adapter" class="danger">Reset Bluetooth adapter</button>
    </div>
  </section>

  <section class="panel">
    <div class="row between" style="margin-bottom:10px">
      <strong>Band battery (manual)</strong>
      <span class="muted">The HR endpoint exposes no Battery Service; read the band screen.</span>
    </div>
    <form id="battery-form">
      <div><label for="battery-percent">Battery %</label><input id="battery-percent" type="number" min="0" max="100" step="1" required></div>
      <div><label for="battery-note">Note</label><input id="battery-note" type="text" placeholder="e.g. broadcast on, 2 h"></div>
      <div><button class="primary" type="submit">Log battery reading</button></div>
    </form>
    <div id="battery-latest" class="muted" style="margin-top:8px">No readings yet.</div>
  </section>

  <section class="panel">
    <div class="row between" style="margin-bottom:10px">
      <strong>Sleep annotations</strong>
      <span class="muted">Approximate; crossing midnight is supported.</span>
    </div>
    <form id="ann-form">
      <div><label for="ann-start">Bedtime</label><input id="ann-start" type="datetime-local" required></div>
      <div><label for="ann-end">Wake-up</label><input id="ann-end" type="datetime-local" required></div>
      <div><label for="ann-confidence">Confidence (0–1)</label><input id="ann-confidence" type="number" min="0" max="1" step="0.05" value="0.7"></div>
      <div><label for="ann-notes">Notes</label><input id="ann-notes" type="text" placeholder="optional"></div>
      <div><button class="primary" type="submit" id="ann-submit">Save sleep period</button></div>
    </form>
    <div id="ann-list" style="margin-top:10px"><div class="muted">No annotations yet.</div></div>
  </section>

  <style>
    .analytics h3 { font-size:15px; margin:18px 0 8px; font-weight:650; }
    .analytics .inline { display:inline-flex; align-items:center; gap:6px; color:var(--muted); font-size:12px; }
    .analytics select, .analytics input[type="datetime-local"] {
      background:#0f151c; color:var(--text); border:1px solid #334252;
      border-radius:8px; padding:6px 8px; font:inherit;
    }
    .analytics .table-wrap {
      overflow:auto; max-height:540px; border:1px solid #263241; border-radius:10px;
    }
    .analytics table { width:100%; border-collapse:collapse; font-size:12px; }
    .analytics th, .analytics td {
      padding:6px 8px; border-bottom:1px solid #263241; text-align:right;
      white-space:nowrap;
    }
    .analytics th {
      position:sticky; top:0; z-index:1; background:var(--panel);
      color:var(--muted); font-weight:600;
    }
    .analytics th.sortable { cursor:pointer; user-select:none; }
    .analytics th.sortable:hover { color:var(--text); }
    .analytics td:first-child, .analytics th:first-child,
    .analytics td:nth-child(2), .analytics th:nth-child(2) { text-align:left; }
    .analytics tbody tr:hover { background:var(--panel2); }
    .analytics tr.clickable { cursor:pointer; }
    .analytics .empty { color:var(--muted); padding:14px; text-align:left; }
    .analytics .warn { color:var(--warn); }
    .analytics .low { color:var(--warn); }
    .analytics [hidden] { display:none !important; }
    .analytics .traj { margin-top:14px; }
    .analytics .traj svg { height:240px; }
  </style>

  <section class="panel analytics" id="analytics">
    <div class="row between" style="margin-bottom:10px">
      <strong>Statistical analytics</strong>
      <span class="muted">Read-only · IST · available data only</span>
    </div>
    <div class="row" style="margin-bottom:10px; gap:10px">
      <label class="inline">Range
        <select id="analytics-range">
          <option value="current_session">Current session</option>
          <option value="1h">Last 1 hour</option>
          <option value="6h">Last 6 hours</option>
          <option value="12h">Last 12 hours</option>
          <option value="24h">Last 24 hours</option>
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="7d">Last 7 days</option>
          <option value="28d">Last 28 days</option>
          <option value="custom">Custom range</option>
        </select>
      </label>
      <span id="analytics-custom" class="row" hidden>
        <label class="inline">From <input id="analytics-start" type="datetime-local"></label>
        <label class="inline">To <input id="analytics-end" type="datetime-local"></label>
        <button id="analytics-apply">Apply</button>
      </span>
      <button id="analytics-refresh">Refresh</button>
      <span id="analytics-range-label" class="muted"></span>
    </div>
    <div id="analytics-warnings" class="warn" style="margin-bottom:8px"></div>
    <div class="cards" id="analytics-summary"></div>

    <h3>Hourly statistics</h3>
    <div class="table-wrap">
      <table id="analytics-hourly"><tbody><tr><td class="empty">Loading…</td></tr></tbody></table>
    </div>
    <p class="muted" id="analytics-hourly-note" style="margin:6px 0 0"></p>

    <h3>Daily statistics</h3>
    <div class="table-wrap">
      <table id="analytics-daily"><tbody><tr><td class="empty">Loading…</td></tr></tbody></table>
    </div>

    <div id="analytics-traj" class="traj" hidden>
      <div class="row between" style="margin-bottom:6px">
        <strong id="analytics-traj-title"></strong>
        <button id="analytics-traj-close">Close</button>
      </div>
      <svg id="analytics-traj-chart" viewBox="0 0 1000 240" preserveAspectRatio="none" role="img" aria-label="Hourly heart-rate trajectory"></svg>
      <div id="analytics-traj-stats" class="muted" style="margin-top:6px"></div>
    </div>
  </section>
</main>
<script>
const $ = (id) => document.getElementById(id);
let windowMinutes = 5;
let points = [];
let disconnects = [];
let annotationCache = [];
let editingId = null;
let batteryReadings = [];

const TZ = 'Asia/Kolkata';
const TZ_OFFSET_MS = 330 * 60 * 1000; // IST is UTC+05:30 with no DST.

function fmtTime(value) {
  if (value == null || value === '') return '—';
  const d = value instanceof Date ? value : new Date(value);
  if (isNaN(d.getTime())) return String(value);
  return d.toLocaleString('en-IN', {
    timeZone: TZ, day:'2-digit', month:'short', year:'numeric',
    hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'
  }) + ' IST';
}
function fmtEpoch(seconds) {
  return seconds ? fmtTime(new Date(seconds * 1000)) : '—';
}
function fmtClockTime(ms) {
  return new Date(ms).toLocaleTimeString('en-IN', {
    timeZone: TZ, hour:'2-digit', minute:'2-digit', hourCycle:'h23'
  });
}
function tickClock() {
  $('clock').textContent = `${fmtClockTime(Date.now())} IST`;
}
function fmtDuration(seconds) {
  if (seconds == null || isNaN(seconds)) return '—';
  seconds = Math.max(0, Math.floor(seconds));
  const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${seconds % 60}s`;
}
function fmtBytes(n) {
  if (!n) return '0 B';
  const units = ['B','KB','MB','GB']; let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}
async function getJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}
function pill(el, text, kind) {
  el.textContent = text;
  el.className = 'pill ' + (kind || text.toLowerCase());
}
async function refreshStatus() {
  try {
    const s = await getJSON('/api/status');
    const state = s.state || {};
    pill($('conn'), state.connection_status || 'unknown');
    $('hr').textContent = state.current_hr == null ? '—' : `${state.current_hr} bpm`;
    $('hr-at').textContent = state.last_measurement_at ? `received ${fmtTime(state.last_measurement_at)}` : 'no data';
    $('rate').textContent = state.sampling_interval_s == null ? '—' : `${Number(state.sampling_interval_s).toFixed(2)} s`;
    $('total').textContent = s.database ? s.database.total_measurements : (state.total_measurements || 0);
    $('db-size').textContent = s.database ? `db ${fmtBytes(s.database.database_bytes)}` : 'database —';
    $('session').textContent = state.session_started_at ? fmtDuration(Date.now()/1000 - state.session_started_at) : '—';
    $('session-id').textContent = state.session_id ? `session ${state.session_id}` : 'session —';
    $('last-conn').textContent = fmtEpoch(state.last_connection_at);
    $('last-disc').textContent = `last disconnect ${fmtEpoch(state.last_disconnection_at)}`;
    $('reconnects').textContent = state.reconnect_attempts || 0;
    $('spool').textContent = `spool ${s.spool_pending || 0}`;
    const adapterBits = [];
    adapterBits.push(state.adapter_available === false ? 'adapter unavailable' : 'adapter ' + (state.adapter_available === true ? 'ok' : '—'));
    if (state.adapter_powered === false) adapterBits.push('powered off');
    if (state.adapter_discovering === true) adapterBits.push('discovery stuck');
    if (state.band_visible === true) adapterBits.push('band nearby');
    if (state.hr_broadcast_active === true) adapterBits.push('HR broadcast on');
    else if (state.hr_broadcast_active === false) adapterBits.push('HR broadcast OFF');
    $('adapter').textContent = adapterBits.join(' · ');
    $('service-line').textContent = `service ${state.service_status || 'unknown'} · ${state.paused ? 'paused' : 'active'}${state.last_error ? ' · ' + state.last_error : ''}`;
    let retry = '';
    if (state.next_retry_at && state.next_retry_at * 1000 > Date.now()) {
      retry = ` Next retry in ${Math.ceil((state.next_retry_at * 1000 - Date.now()) / 1000)} s at ${fmtClockTime(state.next_retry_at * 1000)} IST.`;
    }
    let hint = '';
    const failure = state.last_failure;
    if (state.connection_status === 'connected') {
      hint = '';
    } else if (state.paused) {
      hint = 'Acquisition is paused. Use Start/Connect to resume.';
    } else if (failure === 'hr_broadcast_off') {
      hint = 'Band is nearby, but HR Data Broadcast is OFF. On the band: Settings → HR Data Broadcasts → start.' + retry;
    } else if (failure === 'adapter_powered_off') {
      hint = 'Bluetooth adapter is powered OFF. Turn Bluetooth back on; reconnecting automatically.' + retry;
    } else if (failure === 'adapter_unavailable') {
      hint = 'Bluetooth service/adapter is unavailable. Check that Bluetooth is enabled and the adapter is present.' + retry;
    } else if (failure === 'adapter_discovering' || failure === 'connect_in_progress') {
      hint = 'Bluetooth controller is busy or stuck in discovery. Use “Reset Bluetooth adapter” if this persists.' + retry;
    } else if (failure === 'adapter_reset' || failure === 'adapter_reset_skipped') {
      hint = `Bluetooth adapter recovery: ${state.last_failure_detail || 'done'}.` + retry;
    } else if (failure === 'connect_canceled' || failure === 'connect_timeout' || failure === 'connect_not_found') {
      hint = 'Connect attempt failed at the controller/BlueZ level; retrying automatically.' + retry;
    } else if (failure === 'link_dropped') {
      hint = 'The band dropped the BLE link; reconnecting automatically.' + retry;
    } else if (failure === 'no_packets') {
      hint = 'The link stalled with no HR packets; reconnecting automatically.' + retry;
    } else if (failure === 'band_not_visible') {
      hint = 'HR broadcast endpoint not found. If the band is on, start Settings → HR Data Broadcasts on the band.' + retry;
    } else if (state.last_error) {
      hint = `Not connected: ${state.last_error}` + retry;
    } else {
      hint = 'Waiting for the band HR broadcast endpoint…' + retry;
    }
    $('hint').textContent = hint;
    const servicePill = state.service_status || 'unknown';
    document.querySelectorAll('[data-action]').forEach(b => { b.disabled = false; });
    if (servicePill === 'stopped') $('service-line').textContent += ' · starts on next boot';
  } catch (e) {
    $('service-line').textContent = 'web cannot read acquisition state';
  }
}
function medianInterval() {
  if (points.length < 3) return 1000;
  const gaps = [];
  for (let i=1;i<points.length;i++) {
    const a = new Date(points[i-1].timestamp_utc).getTime();
    const b = new Date(points[i].timestamp_utc).getTime();
    if (b > a) gaps.push(b-a);
  }
  gaps.sort((a,b)=>a-b);
  return gaps[Math.floor(gaps.length/2)] || 1000;
}
function drawChart() {
  const svg = $('chart'), w = 1000, h = 320, ml = 46, mr = 12, mt = 12, mb = 28;
  const now = Date.now();
  const t0 = now - windowMinutes * 60000;
  const yMin = 40, yMax = 180;
  const x = (t) => ml + ((t - t0) / Math.max(1, now - t0)) * (w - ml - mr);
  const y = (v) => mt + ((yMax - Math.min(yMax, Math.max(yMin, v))) / (yMax - yMin)) * (h - mt - mb);

  let grid = '';
  for (const hr of [40,60,80,100,120,140,160,180]) {
    const yy = y(hr);
    grid += `<line class="grid-line" x1="${ml}" y1="${yy}" x2="${w-mr}" y2="${yy}"></line>`;
    grid += `<text class="grid-text" x="4" y="${yy+4}">${hr}</text>`;
  }
  for (let i=0;i<=4;i++) {
    const t = t0 + (now-t0)*(i/4);
    const xx = x(t);
    grid += `<line class="grid-line" x1="${xx}" y1="${mt}" x2="${xx}" y2="${h-mb}"></line>`;
    grid += `<text class="grid-text" x="${xx+3}" y="${h-8}">${fmtClockTime(t)}</text>`;
  }
  $('grid').innerHTML = grid;

  let bands = '';
  for (const d of disconnects) {
    const a = new Date(d.start).getTime(), b = new Date(d.end || new Date()).getTime();
    if (b < t0 || a > now) continue;
    const x1 = x(Math.max(a, t0)), x2 = x(Math.min(b, now));
    if (x2 - x1 < 1) continue;
    bands += `<rect class="gap-band" x="${x1}" y="${mt}" width="${x2-x1}" height="${h-mt-mb}"></rect>`;
    bands += `<line class="gap-edge" x1="${x1}" y1="${mt}" x2="${x1}" y2="${h-mb}"></line>`;
  }
  $('bands').innerHTML = bands;

  const threshold = Math.max(3000, medianInterval() * 2.5);
  let prev = null, segment = '', line = '';
  for (const p of points) {
    const t = new Date(p.timestamp_utc).getTime();
    if (t < t0) continue;
    if (prev !== null && t - prev > threshold) { line += segment; segment = ''; }
    segment += (segment ? 'L' : 'M') + x(t).toFixed(1) + ' ' + y(p.heart_rate_bpm).toFixed(1) + ' ';
    prev = t;
  }
  line += segment;
  $('line').setAttribute('d', line);
  const last = points.length ? points[points.length-1] : null;
  if (last) {
    const t = new Date(last.timestamp_utc).getTime();
    $('last-dot').innerHTML = `<circle cx="${x(t)}" cy="${y(last.heart_rate_bpm)}" r="3.5" fill="#ff7a45"></circle>`;
  } else {
    $('last-dot').innerHTML = '';
  }
}
async function refreshHR() {
  try {
    const data = await getJSON(`/api/hr?minutes=${windowMinutes}`);
    points = data.points || [];
    disconnects = data.disconnects || [];
    drawChart();
  } catch (e) { /* keep the last chart */ }
}
function renderAnnotations() {
  const list = $('ann-list');
  if (!annotationCache.length) { list.innerHTML = '<div class="muted">No annotations yet.</div>'; return; }
  list.innerHTML = annotationCache.map(a => {
    const notes = a.notes ? `<div class="notes">${escapeHtml(a.notes)}</div>` : '';
    return `<div class="ann"><div><div class="when">${fmtTime(a.start_time)} → ${fmtTime(a.end_time)}</div>${notes}</div>
      <div class="row"><button data-edit="${a.annotation_id}">Edit</button><button data-delete="${a.annotation_id}" class="danger">Delete</button></div></div>`;
  }).join('');
  list.querySelectorAll('[data-delete]').forEach(btn => {
    btn.onclick = async () => {
      await fetch(`/api/annotations/${btn.dataset.delete}`, { method:'DELETE' });
      await refreshAnnotations();
    };
  });
  list.querySelectorAll('[data-edit]').forEach(btn => {
    btn.onclick = () => {
      const item = annotationCache.find(a => String(a.annotation_id) === btn.dataset.edit);
      if (!item) return;
      editingId = item.annotation_id;
      $('ann-start').value = toIstInput(item.start_time);
      $('ann-end').value = toIstInput(item.end_time);
      $('ann-confidence').value = item.confidence == null ? 0.7 : item.confidence;
      $('ann-notes').value = item.notes || '';
      $('ann-submit').textContent = 'Update sleep period';
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
  });
}
function toIstInput(iso) {
  const d = new Date(new Date(iso).getTime() + TZ_OFFSET_MS);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}
function istInputToDate(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value || '');
  if (!m) return new Date(NaN);
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) - TZ_OFFSET_MS);
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
async function refreshAnnotations() {
  try { annotationCache = await getJSON('/api/annotations'); renderAnnotations(); } catch (e) {}
}
function renderBattery() {
  if (!batteryReadings.length) {
    $('battery-value').textContent = '—';
    $('battery-at').textContent = 'manual; no BLE service';
    $('battery-latest').textContent = 'No readings yet.';
    return;
  }
  const newest = batteryReadings[0];
  const recent = batteryReadings.filter(
    r => Date.now() - new Date(r.recorded_at).getTime() <= 24 * 3600 * 1000
  );
  const oldest = recent.length ? recent[recent.length - 1] : newest;
  $('battery-value').textContent = newest.percent == null ? '—' : `${newest.percent}%`;
  $('battery-at').textContent = `${fmtTime(newest.recorded_at)}${newest.note ? ' · ' + newest.note : ''}`;
  let text = `Last: ${newest.percent}% at ${fmtTime(newest.recorded_at)}`;
  if (newest.percent != null && oldest.percent != null && newest !== oldest) {
    const hours = (new Date(newest.recorded_at) - new Date(oldest.recorded_at)) / 3600000;
    if (hours >= 1) {
      const rate = (oldest.percent - newest.percent) / hours;
      const perDay = rate * 24;
      const sign = rate >= 0 ? '−' : '+';
      text += ` · ${sign}${Math.abs(rate).toFixed(2)} %/h (${sign}${Math.abs(perDay).toFixed(1)} %/day) over ${hours.toFixed(1)} h`;
    }
  }
  $('battery-latest').textContent = text;
}
async function refreshBattery() {
  try { batteryReadings = await getJSON('/api/battery'); renderBattery(); } catch (e) {}
}
async function control(action) {
  try {
    await getJSON('/api/control', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action}) });
    await refreshStatus();
  } catch (e) { alert('Control failed: ' + e.message); }
}
$('battery-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const percent = parseInt($('battery-percent').value, 10);
  if (!(percent >= 0 && percent <= 100)) { alert('Battery % must be 0–100'); return; }
  const response = await fetch('/api/battery', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ percent, note: $('battery-note').value || null }),
  });
  if (!response.ok) { alert('Could not log battery reading'); return; }
  $('battery-note').value = '';
  await refreshBattery();
});
$('ann-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const start = istInputToDate($('ann-start').value);
  let end = istInputToDate($('ann-end').value);
  if (isNaN(start.getTime()) || isNaN(end.getTime())) { alert('Enter valid IST times'); return; }
  if (end <= start) end = new Date(end.getTime() + 86400000);
  const body = {
    event_type: 'sleep',
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    confidence: parseFloat($('ann-confidence').value || '0.7'),
    notes: $('ann-notes').value || null,
  };
  const url = editingId ? `/api/annotations/${editingId}` : '/api/annotations';
  const method = editingId ? 'PATCH' : 'POST';
  const response = await fetch(url, { method, headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  if (!response.ok) { alert('Could not save annotation'); return; }
  editingId = null;
  $('ann-submit').textContent = 'Save sleep period';
  $('ann-notes').value = '';
  await refreshAnnotations();
});
document.querySelectorAll('[data-window]').forEach(btn => {
  btn.onclick = () => {
    windowMinutes = parseInt(btn.dataset.window, 10);
    document.querySelectorAll('[data-window]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    $('window-label').textContent = `last ${windowMinutes} minute${windowMinutes === 1 ? '' : 's'}`;
    refreshHR();
  };
});
document.querySelectorAll('[data-action]').forEach(btn => {
  btn.onclick = () => {
    if (btn.dataset.action === 'reset_adapter' && !confirm('Power-cycle the Bluetooth adapter?\n\nOther Bluetooth devices will disconnect briefly. The daemon skips the reset if other devices are connected.')) return;
    control(btn.dataset.action);
  };
});
$('export').onclick = () => { window.location = '/api/export.csv'; };
$('restart').onclick = () => control('restart');
refreshStatus(); refreshHR(); refreshAnnotations(); refreshBattery(); tickClock();
setInterval(refreshStatus, 2000);
setInterval(refreshHR, 1000);
setInterval(refreshAnnotations, 10000);
setInterval(refreshBattery, 30000);
setInterval(tickClock, 1000);
</script>
<script>
const $a = (id) => document.getElementById(id);
const A = {
  range: 'current_session',
  data: null,
  hourlySort: { key: 'hour_start_utc', dir: 'asc' },
  dailySort: { key: 'date', dir: 'desc' },
  loading: false,
};

function aNum(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}
function aInt(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return String(Math.round(Number(value)));
}
function aPct(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}
function aClock(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return fmtClockTime(d.getTime());
}
function aCard(label, value, sub) {
  return `<div class="card"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub || '&nbsp;'}</div></div>`;
}

const HOURLY_COLUMNS = [
  { key: 'date', label: 'Date', render: r => r.date },
  { key: 'hour', label: 'Hour', render: r => r.hour },
  { key: 'count', label: 'Count', render: r => aInt(r.count) },
  { key: 'mean', label: 'Mean', render: r => aNum(r.mean) },
  { key: 'median', label: 'Median', render: r => aNum(r.median) },
  { key: 'min', label: 'Min', render: r => aInt(r.min) },
  { key: 'max', label: 'Max', render: r => aInt(r.max) },
  { key: 'sd', label: 'SD', render: r => aNum(r.sd) },
  { key: 'mad', label: 'MAD', render: r => aNum(r.mad) },
  { key: 'iqr', label: 'IQR', render: r => aNum(r.iqr) },
  { key: 'p95', label: 'P95', render: r => aNum(r.p95) },
  { key: 'range', label: 'Range', render: r => aInt(r.range) },
  { key: 'duration_seconds', label: 'Duration', render: r => fmtDuration(r.duration_seconds) },
  { key: 'coverage', label: 'Coverage', render: r => aPct(r.coverage), cls: r => r.low_coverage ? 'low' : '' },
];

const DAILY_COLUMNS = [
  { key: 'date', label: 'Date', render: r => r.date },
  { key: 'count', label: 'Count', render: r => aInt(r.count) },
  { key: 'mean', label: 'Mean', render: r => aNum(r.mean) },
  { key: 'median', label: 'Median', render: r => aNum(r.median) },
  { key: 'min', label: 'Min', render: r => aInt(r.min) },
  { key: 'max', label: 'Max', render: r => aInt(r.max) },
  { key: 'sd', label: 'SD', render: r => aNum(r.sd) },
  { key: 'mad', label: 'MAD', render: r => aNum(r.mad) },
  { key: 'iqr', label: 'IQR', render: r => aNum(r.iqr) },
  { key: 'p95', label: 'P95', render: r => aNum(r.p95) },
  { key: 'coverage', label: 'Coverage', render: r => aPct(r.coverage), cls: r => r.low_coverage ? 'low' : '' },
  { key: 'duration_seconds', label: 'Duration', render: r => fmtDuration(r.duration_seconds) },
  { key: 'min_timestamp_utc', label: 'Min at', render: r => aClock(r.min_timestamp_utc) },
  { key: 'max_timestamp_utc', label: 'Max at', render: r => aClock(r.max_timestamp_utc) },
  { key: 'sustained_5min_min', label: '5m min', render: r => aNum(r.sustained_5min_min) },
  { key: 'sustained_5min_max', label: '5m max', render: r => aNum(r.sustained_5min_max) },
  { key: 'time_weighted_mean', label: 'Time-wtd mean', render: r => aNum(r.time_weighted_mean) },
  { key: 'disconnected_intervals', label: 'Disconnects', render: r => aInt(r.disconnected_intervals) },
];

function aSorted(rows, state) {
  const factor = state.dir === 'asc' ? 1 : -1;
  return rows.slice().sort((left, right) => {
    const a = left[state.key];
    const b = right[state.key];
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    if (typeof a === 'number' && typeof b === 'number') return (a - b) * factor;
    return String(a).localeCompare(String(b)) * factor;
  });
}

function aRenderTable(tableId, columns, rows, state, tableKey) {
  const table = $a(tableId);
  const head = '<thead><tr>' + columns.map(column => {
    const indicator = state.key === column.key ? (state.dir === 'asc' ? ' ▲' : ' ▼') : '';
    return `<th class="sortable" data-key="${column.key}">${column.label}${indicator}</th>`;
  }).join('') + '</tr></thead>';

  if (!rows.length) {
    table.innerHTML = head + `<tbody><tr><td class="empty" colspan="${columns.length}">No data for this range.</td></tr></tbody>`;
    return;
  }

  const body = aSorted(rows, state).map(row => {
    const clickable = tableKey === 'hourlySort' && row.hour_start_utc ? ' clickable' : '';
    const cells = columns.map(column => {
      const extra = typeof column.cls === 'function' ? column.cls(row) : (column.cls || '');
      return `<td class="${extra}">${column.render(row)}</td>`;
    }).join('');
    return `<tr class="${clickable}" data-hour-start="${row.hour_start_utc || ''}" data-hour-end="${row.hour_end_utc || ''}" data-label="${row.label || ''}">${cells}</tr>`;
  }).join('');
  table.innerHTML = head + `<tbody>${body}</tbody>`;

  table.querySelectorAll('th[data-key]').forEach(th => {
    th.onclick = () => {
      const key = th.dataset.key;
      const current = A[tableKey];
      A[tableKey] = {
        key,
        dir: current.key === key && current.dir === 'asc' ? 'desc' : 'asc',
      };
      aRenderTables();
    };
  });
  table.querySelectorAll('tr.clickable').forEach(tr => {
    tr.onclick = () => aLoadTrajectory(tr.dataset.hourStart, tr.dataset.hourEnd, tr.dataset.label);
  });
}

function aRenderTables() {
  const hourly = A.data ? (A.data.hourly || []) : [];
  const daily = A.data ? (A.data.daily || []) : [];
  aRenderTable('analytics-hourly', HOURLY_COLUMNS, hourly, A.hourlySort, 'hourlySort');
  aRenderTable('analytics-daily', DAILY_COLUMNS, daily, A.dailySort, 'dailySort');
  $a('analytics-hourly-note').textContent = hourly.length
    ? `${hourly.length} hourly rows · click a row for its HR trajectory.`
    : 'No hourly rows for this range.';
}

function aRenderSummary(data) {
  const s = data.summary || {};
  $a('analytics-summary').innerHTML = [
    aCard('Samples', aInt(s.count), `recorded ${fmtDuration(s.duration_seconds)}`),
    aCard('Mean HR', s.mean == null ? '—' : `${aNum(s.mean)} bpm`, 'arithmetic mean'),
    aCard('Median HR', s.median == null ? '—' : `${aNum(s.median)} bpm`, '50th percentile'),
    aCard('Minimum', aInt(s.min), 'lowest observation'),
    aCard('Maximum', aInt(s.max), 'highest observation'),
    aCard('SD', aNum(s.sd), 'sample SD'),
    aCard('MAD', aNum(s.mad), 'median absolute deviation'),
    aCard('IQR', aNum(s.iqr), 'P75 − P25'),
    aCard('P05 / P95', `${aNum(s.p05)} / ${aNum(s.p95)}`, 'distribution tails'),
    aCard('CV', s.cv == null ? '—' : `${aNum(s.cv)}%`, 'SD / mean × 100'),
    aCard('Range', aInt(s.range), 'max − min'),
    aCard('Coverage', aPct(s.coverage), 'monitored / period'),
  ].join('');
  $a('analytics-range-label').textContent = `${data.range.label} · ${fmtTime(data.range.start_utc)} → ${fmtTime(data.range.end_utc)}`;
  const warnings = data.warnings || [];
  $a('analytics-warnings').textContent = warnings.join(' · ');
}

function aRender(data) {
  A.data = data;
  aRenderSummary(data);
  aRenderTables();
}

async function aRefresh() {
  if (A.loading) return;
  A.loading = true;
  $a('analytics-refresh').disabled = true;
  try {
    const params = new URLSearchParams({ range: A.range });
    if (A.range === 'custom') {
      const start = istInputToDate($a('analytics-start').value);
      const end = istInputToDate($a('analytics-end').value);
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
        throw new Error('Select valid custom start and end times');
      }
      params.set('start', start.toISOString());
      params.set('end', end.toISOString());
    }
    const data = await getJSON(`/api/analytics?${params.toString()}`);
    aRender(data);
  } catch (error) {
    $a('analytics-warnings').textContent = `Analytics error: ${error.message}`;
  } finally {
    A.loading = false;
    $a('analytics-refresh').disabled = false;
  }
}

async function aLoadTrajectory(start, end, label) {
  if (!start || !end) return;
  $a('analytics-traj').hidden = false;
  $a('analytics-traj-title').textContent = label || 'Hourly trajectory';
  $a('analytics-traj-stats').textContent = 'Loading…';
  try {
    const params = new URLSearchParams({ start, end });
    if (A.data && A.data.range && A.data.range.session_id != null) {
      params.set('session_id', A.data.range.session_id);
    }
    const data = await getJSON(`/api/analytics/trajectory?${params.toString()}`);
    aDrawTrajectory(data);
  } catch (error) {
    $a('analytics-traj-chart').innerHTML = '';
    $a('analytics-traj-stats').textContent = `Trajectory error: ${error.message}`;
  }
}

function aDrawTrajectory(data) {
  const svg = $a('analytics-traj-chart');
  const points = data.points || [];
  if (!points.length) {
    svg.innerHTML = '<text x="20" y="40" class="grid-text">No points in this interval.</text>';
    $a('analytics-traj-stats').textContent = 'No points.';
    return;
  }
  const width = 1000, height = 240, left = 46, right = 12, top = 12, bottom = 28;
  const xMin = new Date(data.range.start_utc).getTime();
  const xMax = new Date(data.range.end_utc).getTime();
  const values = points.map(point => Number(point.heart_rate_bpm));
  let yMin = Math.min(...values), yMax = Math.max(...values);
  const pad = Math.max(4, (yMax - yMin) * 0.15);
  yMin = Math.max(30, Math.floor(yMin - pad));
  yMax = Math.min(220, Math.ceil(yMax + pad));
  if (yMax <= yMin) yMax = yMin + 10;

  const x = (time) => left + ((time - xMin) / Math.max(1, xMax - xMin)) * (width - left - right);
  const y = (bpm) => top + ((yMax - Math.min(yMax, Math.max(yMin, bpm))) / (yMax - yMin)) * (height - top - bottom);

  let content = '';
  for (let i = 0; i <= 4; i++) {
    const value = yMin + (yMax - yMin) * (i / 4);
    const yy = y(value);
    content += `<line class="grid-line" x1="${left}" y1="${yy}" x2="${width - right}" y2="${yy}"></line>`;
    content += `<text class="grid-text" x="4" y="${yy + 4}">${Math.round(value)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const time = xMin + (xMax - xMin) * (i / 4);
    const xx = x(time);
    content += `<line class="grid-line" x1="${xx}" y1="${top}" x2="${xx}" y2="${height - bottom}"></line>`;
    content += `<text class="grid-text" x="${xx + 3}" y="${height - 8}">${aClock(new Date(time).toISOString())}</text>`;
  }

  const intervals = [];
  for (let i = 1; i < points.length; i++) {
    const a = new Date(points[i - 1].timestamp_utc).getTime();
    const b = new Date(points[i].timestamp_utc).getTime();
    if (b > a) intervals.push(b - a);
  }
  intervals.sort((a, b) => a - b);
  const median = intervals.length ? intervals[Math.floor(intervals.length / 2)] : 1000;
  const threshold = Math.max(3000, median * 3);

  let previous = null;
  let segment = '';
  let line = '';
  for (const point of points) {
    const time = new Date(point.timestamp_utc).getTime();
    if (previous !== null && time - previous > threshold) {
      line += segment;
      segment = '';
    }
    segment += `${segment ? 'L' : 'M'}${x(time).toFixed(1)} ${y(point.heart_rate_bpm).toFixed(1)} `;
    previous = time;
  }
  line += segment;
  content += `<path class="hr-line" d="${line}"></path>`;
  const last = points[points.length - 1];
  content += `<circle cx="${x(new Date(last.timestamp_utc).getTime())}" cy="${y(last.heart_rate_bpm)}" r="3.5" fill="#ff7a45"></circle>`;
  svg.innerHTML = content;
  const s = data.summary || {};
  $a('analytics-traj-stats').textContent = `n=${aInt(s.count)} · mean ${aNum(s.mean)} bpm · min ${aInt(s.min)} · max ${aInt(s.max)} · SD ${aNum(s.sd)}`;
}

$a('analytics-range').addEventListener('change', () => {
  A.range = $a('analytics-range').value;
  $a('analytics-custom').hidden = A.range !== 'custom';
  if (A.range !== 'custom') aRefresh();
});
$a('analytics-apply').onclick = () => aRefresh();
$a('analytics-refresh').onclick = () => aRefresh();
$a('analytics-traj-close').onclick = () => { $a('analytics-traj').hidden = true; };

(function aInit() {
  const now = new Date();
  $a('analytics-start').value = toIstInput(new Date(now.getTime() - 24 * 3600 * 1000).toISOString());
  $a('analytics-end').value = toIstInput(now.toISOString());
  aRefresh();
  setInterval(aRefresh, 30000);
})();
</script>
</body>
</html>
"""
