"""Single-page acquisition dashboard (no external JS/CSS dependencies)."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Band 9 Acquisition</title>
<link rel="icon" href="data:,">
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
      <strong>Band battery and charging</strong>
      <span class="muted">The HR endpoint exposes no Battery Service; log readings and charges from the band screen.</span>
    </div>
    <form id="battery-form">
      <div><label for="battery-percent">Current battery %</label><input id="battery-percent" type="number" min="0" max="100" step="1" required></div>
      <div><label for="battery-note">Note</label><input id="battery-note" type="text" placeholder="e.g. broadcast on, 2 h"></div>
      <div><button class="primary" type="submit">Log battery reading</button></div>
    </form>
    <div id="battery-latest" class="muted" style="margin-top:8px">No readings yet.</div>

    <div style="border-top:1px solid #263241; margin:16px 0 12px"></div>
    <div class="row between" style="margin-bottom:10px">
      <strong>Charging</strong>
      <span class="muted">Log after charging ends. A charge event resets the drain baseline; optional minutes enable charge-rate history.</span>
    </div>
    <form id="charge-form">
      <div><label for="charge-to">Charged to %</label><input id="charge-to" type="number" min="0" max="100" step="1" required></div>
      <div><label for="charge-from">From % (optional)</label><input id="charge-from" type="number" min="0" max="100" step="1" placeholder="auto: latest reading"></div>
      <div><label for="charge-minutes">Charge time (min, optional)</label><input id="charge-minutes" type="number" min="0" step="1" placeholder="e.g. 45"></div>
      <div><label for="charge-note">Note</label><input id="charge-note" type="text" placeholder="e.g. daily fixed charge"></div>
      <div><button class="primary" type="submit">Log charge</button></div>
    </form>
    <div id="battery-charge-latest" class="muted" style="margin-top:8px">No charge events yet.</div>
    <div id="battery-charge-history" class="muted" style="margin-top:6px"></div>
    <div id="battery-warnings" class="muted" style="margin-top:6px"></div>
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
    .analytics .charts {
      display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
      gap:16px; margin-bottom:8px;
    }
    @media (max-width:760px) {
      .analytics .charts { grid-template-columns:1fr; }
    }
    .analytics .chart-card {
      background:var(--panel); border:1px solid #263241; border-radius:10px;
      padding:10px;
    }
    .analytics .chart-title { font-size:13px; font-weight:600; margin-bottom:6px; }
    .analytics .chart-card svg, .analytics > svg {
      width:100%; height:auto; background:#0d1218; border:1px solid #263241;
      border-radius:10px; display:block;
    }
    .analytics .wide { min-width:320px; width:min(560px,70vw); }
    .analytics .legend {
      display:flex; gap:14px; flex-wrap:wrap; color:var(--muted);
      font-size:12px; margin:8px 0;
    }
    .analytics .legend i {
      display:inline-block; width:10px; height:10px; border-radius:2px;
      margin-right:6px; vertical-align:-1px;
    }
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

    <h3>HR distribution</h3>
    <div class="row" style="margin-bottom:8px">
      <label class="inline">Bin width
        <select id="analytics-bin-width">
          <option value="2">2 bpm</option>
          <option value="5" selected>5 bpm</option>
          <option value="10">10 bpm</option>
        </select>
      </label>
      <span class="muted">Histogram, ECDF, box plot and hourly P05–P95 bands.</span>
    </div>
    <div class="charts">
      <div class="chart-card"><div class="chart-title">Histogram</div><svg id="analytics-histogram" viewBox="0 0 500 220"></svg></div>
      <div class="chart-card"><div class="chart-title">ECDF</div><svg id="analytics-ecdf" viewBox="0 0 500 220"></svg></div>
      <div class="chart-card"><div class="chart-title">Box plot</div><svg id="analytics-box" viewBox="0 0 500 220"></svg></div>
      <div class="chart-card"><div class="chart-title">Hourly P05–P95</div><svg id="analytics-percentile" viewBox="0 0 500 220"></svg></div>
    </div>
    <div id="analytics-distribution-note" class="muted"></div>

    <h3>HR bands</h3>
    <div class="row" style="margin-bottom:8px">
      <label class="inline">Intervals <input id="analytics-bands-input" class="wide" type="text"></label>
      <button id="analytics-bands-apply">Apply</button>
      <button id="analytics-bands-reset">Reset</button>
      <span class="muted">Descriptive intervals only; not diagnostic or exercise-intensity labels.</span>
    </div>
    <div class="table-wrap"><table id="analytics-bands-table"></table></div>
    <svg id="analytics-bands-chart" viewBox="0 0 1000 240"></svg>
    <div id="analytics-bands-legend" class="legend"></div>

    <h3>Sleep statistics</h3>
    <div id="analytics-sleep-note" class="muted"></div>
    <div class="table-wrap"><table id="analytics-sleep-table"></table></div>
    <svg id="analytics-sleep-chart" viewBox="0 0 1000 240"></svg>
    <div id="analytics-sleep-legend" class="legend"></div>

    <h3>Circadian heatmap</h3>
    <div class="row" style="margin-bottom:8px">
      <label class="inline">Metric
        <select id="analytics-heatmap-metric">
          <option value="mean">Mean HR</option>
          <option value="median">Median HR</option>
          <option value="sd">SD</option>
          <option value="mad">MAD</option>
          <option value="p95">P95</option>
        </select>
      </label>
      <span class="muted">Date × local hour; empty cells are not imputed.</span>
    </div>
    <svg id="analytics-heatmap" viewBox="0 0 1000 380"></svg>

    <h3>Rolling baseline</h3>
    <div class="cards" id="analytics-baseline-summary"></div>
    <svg id="analytics-baseline-chart" viewBox="0 0 1000 260"></svg>
    <div id="analytics-baseline-legend" class="legend"></div>
    <div id="analytics-baseline-note" class="muted"></div>

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
let batterySummary = null;

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
function drainBasisLabel(basis) {
  if (basis === 'since_last_charge') return 'since last charge';
  if (basis === 'last_24h') return 'over last 24 h';
  return 'over all readings';
}
function renderBattery() {
  const summary = batterySummary;
  if (!summary || !summary.display) {
    $('battery-value').textContent = '—';
    $('battery-at').textContent = 'manual; no BLE service';
  } else {
    const kind = summary.display.kind === 'charge' ? ' · after charge' : '';
    $('battery-value').textContent = `${summary.display.percent}%`;
    $('battery-at').textContent = `${fmtTime(summary.display.recorded_at)}${summary.display.note ? ' · ' + summary.display.note : ''}${kind}`;
  }

  let text = 'No readings yet.';
  if (summary && summary.latest_reading) {
    const reading = summary.latest_reading;
    text = `Last reading: ${reading.percent}% at ${fmtTime(reading.recorded_at)}`;
  }
  const drain = summary && summary.drain;
  if (drain && drain.available) {
    const rate = drain.drain_percent_per_hour;
    const sign = rate >= 0 ? '−' : '+';
    text += ` · ${sign}${Math.abs(rate).toFixed(2)} %/h (${sign}${Math.abs(drain.drain_percent_per_day).toFixed(1)} %/day) ${drainBasisLabel(drain.basis)}`;
  } else if (drain && drain.reason) {
    text += ` · drain unavailable: ${drain.reason}`;
  }
  $('battery-latest').textContent = text;

  const charge = summary && summary.latest_charge;
  if (!charge) {
    $('battery-charge-latest').textContent = 'No charge events yet.';
  } else {
    let ctext = 'Last charge: ';
    if (charge.from_percent != null) ctext += `${charge.from_percent}% → `;
    ctext += `${charge.to_percent}% at ${fmtTime(charge.recorded_at)}`;
    if (charge.duration_minutes != null) ctext += ` · ${charge.duration_minutes} min`;
    if (charge.charge_rate_percent_per_hour != null) ctext += ` · +${charge.charge_rate_percent_per_hour.toFixed(1)} %/h`;
    $('battery-charge-latest').textContent = ctext;
  }

  const charges = (summary && summary.charges) || [];
  $('battery-charge-history').innerHTML = charges.slice(0, 5).map(item => {
    const path = item.from_percent != null ? `${item.from_percent}% → ${item.to_percent}%` : `to ${item.to_percent}%`;
    const duration = item.duration_minutes != null ? ` · ${item.duration_minutes} min` : '';
    const rate = item.charge_rate_percent_per_hour != null ? ` · +${item.charge_rate_percent_per_hour.toFixed(1)} %/h` : '';
    const note = item.note ? ` · ${escapeHtml(item.note)}` : '';
    return `${escapeHtml(`· ${path}${duration}${rate} — ${fmtTime(item.recorded_at)}`)}${note}`;
  }).join('<br>');

  const warnings = (summary && summary.warnings) || [];
  $('battery-warnings').textContent = warnings.length ? warnings.join(' · ') : '';
}
async function refreshBattery() {
  try { batterySummary = await getJSON('/api/battery/summary'); renderBattery(); } catch (e) {}
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
$('charge-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const toPercent = parseInt($('charge-to').value, 10);
  if (!(toPercent >= 0 && toPercent <= 100)) { alert('Charged-to % must be 0–100'); return; }
  const fromRaw = $('charge-from').value.trim();
  const fromPercent = fromRaw === '' ? null : parseInt(fromRaw, 10);
  if (fromPercent != null && !(fromPercent >= 0 && fromPercent <= 100)) { alert('From % must be 0–100'); return; }
  const minutesRaw = $('charge-minutes').value.trim();
  const durationMinutes = minutesRaw === '' ? null : parseFloat(minutesRaw);
  if (durationMinutes != null && !(durationMinutes >= 0)) { alert('Charge time must be zero or more minutes'); return; }
  const response = await fetch('/api/battery/charge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      to_percent: toPercent,
      from_percent: fromPercent,
      duration_minutes: durationMinutes,
      note: $('charge-note').value || null,
    }),
  });
  if (!response.ok) {
    let detail = 'Could not log charge';
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch (e) {}
    alert(detail);
    return;
  }
  $('charge-to').value = '';
  $('charge-from').value = '';
  $('charge-minutes').value = '';
  $('charge-note').value = '';
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
  binWidth: 5,
  bands: '',
  heatmapMetric: 'mean',
  loading: false,
  refreshQueued: false,
};
const DEFAULT_BANDS_TEXT = '<50,50-59,60-69,70-79,80-89,90-99,100-109,110-119,120+';

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

function aMessage(id, text) {
  const svg = $a(id);
  svg.innerHTML = `<text x="16" y="28" class="grid-text">${escapeHtml(text)}</text>`;
}
function aShortTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('en-IN', {
    timeZone: TZ, day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
}
function aShortDate(dateText) {
  const d = new Date(`${dateText}T00:00:00+05:30`);
  if (Number.isNaN(d.getTime())) return dateText;
  return d.toLocaleDateString('en-IN', {
    timeZone: TZ, day: '2-digit', month: 'short',
  });
}
function aColor(t) {
  const value = Math.max(0, Math.min(1, t));
  const low = [38, 52, 78];
  const high = [255, 122, 69];
  const rgb = low.map((v, i) => Math.round(v + (high[i] - v) * value));
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}
function aGrid({ w, h, left, right, top, bottom, xMin, xMax, yMin, yMax, xTicks = 4, yTicks = 4, xLabel, yLabel }) {
  const dx = w - left - right;
  const dy = h - top - bottom;
  let output = '';
  for (let i = 0; i <= yTicks; i++) {
    const value = yMin + (yMax - yMin) * (i / Math.max(1, yTicks));
    const yy = top + dy * (1 - i / Math.max(1, yTicks));
    output += `<line class="grid-line" x1="${left}" y1="${yy}" x2="${w - right}" y2="${yy}"></line>`;
    output += `<text class="grid-text" x="4" y="${yy + 4}">${yLabel ? yLabel(value) : Math.round(value)}</text>`;
  }
  for (let i = 0; i <= xTicks; i++) {
    const value = xMin + (xMax - xMin) * (i / Math.max(1, xTicks));
    const xx = left + dx * (i / Math.max(1, xTicks));
    output += `<line class="grid-line" x1="${xx}" y1="${top}" x2="${xx}" y2="${h - bottom}"></line>`;
    output += `<text class="grid-text" x="${Math.min(xx + 3, w - right - 44)}" y="${h - 8}">${xLabel ? xLabel(value) : ''}</text>`;
  }
  return output;
}
function aPath(points, x, y, threshold) {
  if (!points.length) return '';
  let output = '';
  let segment = '';
  let previous = null;
  for (const point of points) {
    if (previous !== null && point.t - previous > threshold) {
      output += segment;
      segment = '';
    }
    segment += `${segment ? 'L' : 'M'}${x(point.t).toFixed(1)} ${y(point.v).toFixed(1)} `;
    previous = point.t;
  }
  return output + segment;
}

function aRenderDistribution(data) {
  const available = data && data.available;
  const warnings = data && data.warnings ? data.warnings : [];
  $a('analytics-distribution-note').textContent = available
    ? `${data.ecdf.total} samples · ${warnings.join(' · ')}`
    : 'No distribution data for this range.';

  const hist = data && data.histogram;
  if (!available || !hist || !hist.available || !hist.bins.length) {
    aMessage('analytics-histogram', 'No histogram data.');
  } else {
    const w = 500, h = 220, left = 42, right = 8, top = 12, bottom = 26;
    const bins = hist.bins;
    const xMin = bins[0].start, xMax = bins[bins.length - 1].end;
    const yMax = Math.max(1, ...bins.map(bin => bin.count));
    const x = value => left + ((value - xMin) / Math.max(1, xMax - xMin)) * (w - left - right);
    const y = count => top + (1 - count / yMax) * (h - top - bottom);
    let content = aGrid({
      w, h, left, right, top, bottom, xMin, xMax, yMin: 0, yMax,
      xTicks: 5, yTicks: 4,
      xLabel: value => Math.round(value),
      yLabel: value => Math.round(value),
    });
    for (const bin of bins) {
      const x1 = x(bin.start), x2 = x(bin.end);
      const yy = y(bin.count);
      content += `<rect x="${x1}" y="${yy}" width="${Math.max(1, x2 - x1 - 1)}" height="${h - bottom - yy}" fill="#ff7a45" opacity="0.82"><title>${bin.label}: ${bin.count}</title></rect>`;
    }
    $a('analytics-histogram').innerHTML = content;
  }

  const ecdfData = data && data.ecdf;
  if (!available || !ecdfData || !ecdfData.available || !ecdfData.points.length) {
    aMessage('analytics-ecdf', 'No ECDF data.');
  } else {
    const w = 500, h = 220, left = 42, right = 8, top = 12, bottom = 26;
    const points = ecdfData.points;
    const xMin = points[0].bpm, xMax = points[points.length - 1].bpm;
    const x = value => left + ((value - xMin) / Math.max(1, xMax - xMin)) * (w - left - right);
    const y = value => top + (1 - value) * (h - top - bottom);
    let content = aGrid({
      w, h, left, right, top, bottom, xMin, xMax, yMin: 0, yMax: 1,
      xTicks: 5, yTicks: 4,
      xLabel: value => Math.round(value),
      yLabel: value => `${Math.round(value * 100)}%`,
    });
    let path = `M${x(points[0].bpm).toFixed(1)} ${y(0).toFixed(1)}`;
    for (const point of points) {
      path += `H${x(point.bpm).toFixed(1)} V${y(point.proportion).toFixed(1)}`;
    }
    content += `<path class="hr-line" d="${path}"></path>`;
    $a('analytics-ecdf').innerHTML = content;
  }

  const box = data && data.box;
  if (!available || !box) {
    aMessage('analytics-box', 'No box statistics.');
  } else {
    const w = 500, h = 220, left = 42, right = 8, top = 34, bottom = 26;
    const xMin = box.min, xMax = box.max;
    const x = value => left + ((value - xMin) / Math.max(1, xMax - xMin)) * (w - left - right);
    const center = top + (h - top - bottom) / 2;
    let content = aGrid({
      w, h, left, right, top, bottom, xMin, xMax, yMin: 0, yMax: 1,
      xTicks: 5, yTicks: 0,
      xLabel: value => Math.round(value),
    });
    content += `<line class="grid-line" x1="${x(box.whisker_low)}" y1="${center}" x2="${x(box.whisker_high)}" y2="${center}"></line>`;
    content += `<line class="grid-line" x1="${x(box.whisker_low)}" y1="${center - 16}" x2="${x(box.whisker_low)}" y2="${center + 16}"></line>`;
    content += `<line class="grid-line" x1="${x(box.whisker_high)}" y1="${center - 16}" x2="${x(box.whisker_high)}" y2="${center + 16}"></line>`;
    content += `<rect x="${x(box.q1)}" y="${center - 30}" width="${Math.max(1, x(box.q3) - x(box.q1))}" height="60" fill="#2b3745" stroke="#ff7a45"></rect>`;
    content += `<line x1="${x(box.median)}" y1="${center - 30}" x2="${x(box.median)}" y2="${center + 30}" stroke="#ff7a45" stroke-width="2"></line>`;
    for (const outlier of box.outliers) {
      content += `<circle cx="${x(outlier)}" cy="${center}" r="2.5" fill="#ff5d5d"></circle>`;
    }
    content += `<text class="grid-text" x="${left}" y="18">n=${box.count} · Q1 ${box.q1} · median ${box.median} · Q3 ${box.q3} · outliers ${box.outlier_count}</text>`;
    $a('analytics-box').innerHTML = content;
  }

  const bands = data && data.percentile_bands;
  if (!available || !bands || !bands.length) {
    aMessage('analytics-percentile', 'No hourly percentile bands.');
  } else {
    const w = 500, h = 220, left = 42, right = 8, top = 12, bottom = 26;
    const times = bands.map(row => new Date(row.timestamp_utc).getTime());
    const xMin = Math.min(...times), xMax = Math.max(...times);
    const values = bands.flatMap(row => [row.p05, row.p95]).filter(value => value != null);
    const yMin = Math.min(...values) - 2, yMax = Math.max(...values) + 2;
    const x = value => left + ((value - xMin) / Math.max(1, xMax - xMin)) * (w - left - right);
    const y = value => top + (1 - (value - yMin) / Math.max(1, yMax - yMin)) * (h - top - bottom);
    let content = aGrid({
      w, h, left, right, top, bottom, xMin, xMax, yMin, yMax,
      xTicks: 4, yTicks: 4,
      xLabel: value => aClock(new Date(value).toISOString()),
      yLabel: value => Math.round(value),
    });
    const topPoints = bands.map(row => ({ t: new Date(row.timestamp_utc).getTime(), v: row.p95 }));
    const bottomPoints = bands.map(row => ({ t: new Date(row.timestamp_utc).getTime(), v: row.p05 })).reverse();
    if (topPoints.length > 1) {
      const area = `${aPath(topPoints, x, y, 1e15)}L${bottomPoints.map(point => `${x(point.t).toFixed(1)} ${y(point.v).toFixed(1)}`).join('L')}Z`;
      content += `<path d="${area}" fill="rgba(255,122,69,0.16)" stroke="none"></path>`;
    }
    const medianPoints = bands.map(row => ({ t: new Date(row.timestamp_utc).getTime(), v: row.median }));
    content += `<path class="hr-line" d="${aPath(medianPoints, x, y, 1e15)}"></path>`;
    $a('analytics-percentile').innerHTML = content;
  }
}

function aStaticTable(tableId, columns, rows, emptyText) {
  const table = $a(tableId);
  const head = '<thead><tr>' + columns.map(column => `<th>${column.label}</th>`).join('') + '</tr></thead>';
  if (!rows.length) {
    table.innerHTML = head + `<tbody><tr><td class="empty" colspan="${columns.length}">${emptyText || 'No data.'}</td></tr></tbody>`;
    return;
  }
  table.innerHTML = head + '<tbody>' + rows.map(row => '<tr>' + columns.map(column => `<td>${column.render(row)}</td>`).join('') + '</tr>').join('') + '</tbody>';
}

const BAND_COLORS = ['#5b8ff9', '#61ddaa', '#f6bd16', '#ff9845', '#ff6b6b', '#b37feb', '#36cfc9', '#ffc069', '#9254de', '#597ef7'];

function aRenderBands(data) {
  const bands = data && data.bands ? data.bands : [];
  aStaticTable('analytics-bands-table', [
    { label: 'Interval', render: row => escapeHtml(row.label) },
    { label: 'Duration', render: row => fmtDuration(row.duration_seconds) },
    { label: '% monitored', render: row => `${aNum(row.percentage)}%` },
    { label: 'Episodes', render: row => aInt(row.episodes) },
    { label: 'Longest', render: row => fmtDuration(row.longest_episode_seconds) },
  ], bands, 'No band data.');
  $a('analytics-bands-legend').innerHTML = bands.map((band, index) =>
    `<span><i style="background:${BAND_COLORS[index % BAND_COLORS.length]}"></i>${escapeHtml(band.label)}</span>`
  ).join('');

  if (!data || !data.available || !data.daily || !data.daily.length) {
    aMessage('analytics-bands-chart', 'No daily band data.');
    return;
  }
  const dates = data.daily.map(row => row.date);
  const totals = data.daily.map(row => Object.values(row.values).reduce((sum, value) => sum + value, 0));
  const maxHours = Math.max(0.1, ...totals.map(seconds => seconds / 3600));
  const w = 1000, h = 240, left = 42, right = 8, top = 12, bottom = 26;
  const xStep = (w - left - right) / Math.max(1, dates.length);
  const barWidth = Math.max(4, xStep * 0.68);
  const y = hours => top + (1 - hours / maxHours) * (h - top - bottom);
  let content = aGrid({
    w, h, left, right, top, bottom, xMin: 0, xMax: 1, yMin: 0, yMax: maxHours,
    xTicks: 0, yTicks: 4, yLabel: value => `${aNum(value, 1)}h`,
  });
  const labelEvery = Math.max(1, Math.ceil(dates.length / 8));
  data.daily.forEach((row, dateIndex) => {
    const x = left + dateIndex * xStep + (xStep - barWidth) / 2;
    let cumulative = 0;
    bands.forEach((band, bandIndex) => {
      const hours = (row.values[band.id] || 0) / 3600;
      if (hours <= 0) return;
      const yTop = y(cumulative + hours);
      const height = Math.max(0.5, y(cumulative) - yTop);
      content += `<rect x="${x}" y="${yTop}" width="${barWidth}" height="${height}" fill="${BAND_COLORS[bandIndex % BAND_COLORS.length]}"><title>${row.date} · ${band.label}: ${aNum(hours, 2)} h</title></rect>`;
      cumulative += hours;
    });
    if (dateIndex % labelEvery === 0) {
      content += `<text class="grid-text" x="${x}" y="${h - 8}">${aShortDate(row.date)}</text>`;
    }
  });
  $a('analytics-bands-chart').innerHTML = content;
}

function aRenderSleep(data) {
  const available = data && data.available;
  const note = !available
    ? (data && (data.reason || data.note)) || 'No sleep annotations.'
    : `${data.nights_with_data}/${data.nights} annotated nights with data · ${(data.warnings || []).join(' · ')}`;
  $a('analytics-sleep-note').textContent = note;

  const history = data && data.history ? data.history : [];
  aStaticTable('analytics-sleep-table', [
    { label: 'Date', render: row => row.start_local ? row.start_local.slice(0, 10) : '—' },
    { label: 'Start', render: row => aClock(row.start_utc) },
    { label: 'End', render: row => aClock(row.end_utc) },
    { label: 'Hours', render: row => aNum(row.duration_hours, 2) },
    { label: 'Count', render: row => aInt(row.count) },
    { label: 'Mean', render: row => aNum(row.mean) },
    { label: 'Median', render: row => aNum(row.median) },
    { label: 'Min', render: row => aInt(row.min) },
    { label: 'Max', render: row => aInt(row.max) },
    { label: 'SD', render: row => aNum(row.sd) },
    { label: 'MAD', render: row => aNum(row.mad) },
    { label: 'IQR', render: row => aNum(row.iqr) },
    { label: 'P05', render: row => aNum(row.p05) },
    { label: 'P95', render: row => aNum(row.p95) },
    { label: '5m min', render: row => aNum(row.sustained_5min_min) },
    { label: 'Nadir', render: row => aInt(row.nadir_bpm) },
    { label: 'Nadir min', render: row => aNum(row.nadir_time_min) },
    { label: 'Awake rest', render: row => aNum(row.awake_resting) },
    { label: 'Δ vs awake', render: row => aNum(row.delta_vs_awake) },
  ], history, 'No annotated nights with HR data.');

  if (!available || !data.aligned || !data.aligned.length) {
    $a('analytics-sleep-legend').innerHTML = '';
    aMessage('analytics-sleep-chart', 'No sleep-aligned trajectory.');
    return;
  }
  const w = 1000, h = 240, left = 42, right = 8, top = 12, bottom = 26;
  const allPoints = data.aligned.flatMap(night => night.points.map(point => ({ t: point.minute, v: point.hr })));
  if (!allPoints.length) {
    aMessage('analytics-sleep-chart', 'No sleep HR points.');
    return;
  }
  const xMin = 0, xMax = Math.max(1, ...allPoints.map(point => point.t));
  const yMin = Math.min(...allPoints.map(point => point.v)) - 2;
  const yMax = Math.max(...allPoints.map(point => point.v)) + 2;
  const x = value => left + (value / Math.max(1, xMax)) * (w - left - right);
  const y = value => top + (1 - (value - yMin) / Math.max(1, yMax - yMin)) * (h - top - bottom);
  let content = aGrid({
    w, h, left, right, top, bottom, xMin, xMax, yMin, yMax,
    xTicks: 5, yTicks: 4,
    xLabel: value => `${Math.round(value)}m`,
    yLabel: value => Math.round(value),
  });
  for (const night of data.aligned) {
    if (!night.points.length) continue;
    const points = night.points.map(point => ({ t: point.minute, v: point.hr }));
    content += `<path d="${aPath(points, x, y, 1e15)}" fill="none" stroke="#5b8ff9" stroke-width="1" opacity="0.22"></path>`;
  }
  const meanPoints = data.mean_trajectory.map(point => ({ t: point.minute, v: point.hr }));
  content += `<path class="hr-line" d="${aPath(meanPoints, x, y, 1e15)}"></path>`;
  $a('analytics-sleep-chart').innerHTML = content;
  $a('analytics-sleep-legend').innerHTML = '<span><i style="background:#ff7a45"></i>Mean across nights</span><span><i style="background:#5b8ff9"></i>Individual nights</span>';
}

function aRenderHeatmap(data) {
  if (!data || !data.available || !data.dates.length) {
    aMessage('analytics-heatmap', 'No heatmap data.');
    return;
  }
  const metric = A.heatmapMetric;
  const values = data.cells.map(cell => cell[metric]).filter(value => value != null);
  if (!values.length) {
    aMessage('analytics-heatmap', `No ${metric} values.`);
    return;
  }
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const span = Math.max(0.001, maximum - minimum);
  const lookup = new Map(data.cells.map(cell => [`${cell.date}|${cell.hour}`, cell]));
  const w = 1000, h = 380, left = 44, right = 8, top = 26, bottom = 28;
  const cellW = (w - left - right) / Math.max(1, data.dates.length);
  const cellH = (h - top - bottom) / 24;
  let content = '';
  const labelEveryDate = Math.max(1, Math.ceil(data.dates.length / 8));
  data.dates.forEach((date, dateIndex) => {
    if (dateIndex % labelEveryDate === 0) {
      content += `<text class="grid-text" x="${left + dateIndex * cellW}" y="${h - 8}">${aShortDate(date)}</text>`;
    }
    for (let hour = 0; hour < 24; hour++) {
      const cell = lookup.get(`${date}|${hour}`);
      const value = cell ? cell[metric] : null;
      const x = left + dateIndex * cellW;
      const y = top + hour * cellH;
      const fill = value == null ? '#151b23' : aColor((value - minimum) / span);
      const title = cell ? `${date} ${String(hour).padStart(2, '0')}:00 · ${metric}=${aNum(value)} · n=${cell.count}` : `${date} ${String(hour).padStart(2, '0')}:00 · no data`;
      content += `<rect x="${x}" y="${y}" width="${Math.max(1, cellW - 1)}" height="${Math.max(1, cellH - 1)}" fill="${fill}"><title>${escapeHtml(title)}</title></rect>`;
    }
  });
  for (const hour of [0, 6, 12, 18, 23]) {
    content += `<text class="grid-text" x="4" y="${top + hour * cellH + 10}">${String(hour).padStart(2, '0')}</text>`;
  }
  content += `<text class="grid-text" x="${left}" y="16">${metric.toUpperCase()} HR · dates × local hour · ${data.dates.length} days</text>`;
  $a('analytics-heatmap').innerHTML = content;
}

function aRenderBaseline(data) {
  if (!data || !data.available) {
    $a('analytics-baseline-summary').innerHTML = aCard('Baseline', '—', 'No data for this range.');
    $a('analytics-baseline-legend').innerHTML = '';
    aMessage('analytics-baseline-chart', 'No rolling baseline data.');
    $a('analytics-baseline-note').textContent = data && data.warnings ? data.warnings.join(' · ') : '';
    return;
  }
  const baselines = data.baselines || {};
  const series = data.series || [];
  const latest = key => {
    for (let index = series.length - 1; index >= 0; index--) {
      if (series[index][key] != null) return series[index][key];
    }
    return null;
  };
  const cards = [
    aCard('Resting proxy', baselines.resting ? `${aNum(baselines.resting.bpm)} bpm` : '—', baselines.resting ? baselines.resting.method : 'unavailable'),
    aCard('Sleep baseline', baselines.sleep ? `${aNum(baselines.sleep.bpm)} bpm` : '—', baselines.sleep ? `${baselines.sleep.nights} nights` : 'no sleep annotations'),
    aCard('Overall median', aNum(baselines.overall ? baselines.overall.median : null), 'provisional'),
    aCard('MAD', aNum(baselines.overall ? baselines.overall.mad : null), 'robust spread'),
    aCard('Days', aInt(baselines.days), baselines.provisional ? 'provisional' : 'baseline'),
    aCard('Trend', data.trend ? `${aNum(data.trend.slope_bpm_per_day, 2)} bpm/day` : '—', data.trend ? `OLS, R²=${aNum(data.trend.r2, 2)}` : 'needs ≥2 days'),
  ];
  for (const window of ['1h', '6h', '24h', '7d', '28d']) {
    const mean = latest(`mean_${window}`);
    const median = latest(`median_${window}`);
    cards.push(aCard(`${window} rolling`, `${aNum(mean)} / ${aNum(median)}`, 'mean / median'));
  }
  $a('analytics-baseline-summary').innerHTML = cards.join('');
  $a('analytics-baseline-note').textContent = `${(data.warnings || []).join(' · ')}${baselines.note ? ' · ' + baselines.note : ''}`;

  if (!series.length) {
    $a('analytics-baseline-legend').innerHTML = '';
    aMessage('analytics-baseline-chart', 'Rolling windows are not populated yet.');
    return;
  }
  const w = 1000, h = 260, left = 42, right = 8, top = 12, bottom = 26;
  const times = series.map(row => new Date(row.timestamp_utc).getTime());
  const xMin = Math.min(...times), xMax = Math.max(...times);
  const allValues = [];
  for (const row of series) {
    for (const key of ['mean_1h', 'mean_6h', 'mean_24h', 'mean_7d', 'mean_28d']) {
      if (row[key] != null) allValues.push(row[key]);
    }
  }
  if (!allValues.length) {
    aMessage('analytics-baseline-chart', 'Rolling windows are not populated yet.');
    return;
  }
  const yMin = Math.min(...allValues) - 2, yMax = Math.max(...allValues) + 2;
  const x = value => left + ((value - xMin) / Math.max(1, xMax - xMin)) * (w - left - right);
  const y = value => top + (1 - (value - yMin) / Math.max(1, yMax - yMin)) * (h - top - bottom);
  let content = aGrid({
    w, h, left, right, top, bottom, xMin, xMax, yMin, yMax,
    xTicks: 4, yTicks: 4,
    xLabel: value => aShortTime(new Date(value).toISOString()),
    yLabel: value => Math.round(value),
  });
  const windows = [
    ['mean_1h', '#ff7a45'], ['mean_6h', '#f6bd16'], ['mean_24h', '#61ddaa'],
    ['mean_7d', '#5b8ff9'], ['mean_28d', '#b37feb'],
  ];
  for (const [key, color] of windows) {
    const points = series
      .filter(row => row[key] != null)
      .map(row => ({ t: new Date(row.timestamp_utc).getTime(), v: row[key] }));
    if (points.length) {
      content += `<path d="${aPath(points, x, y, 2 * 3600 * 1000)}" fill="none" stroke="${color}" stroke-width="2" opacity="0.9"></path>`;
    }
  }
  if (baselines.resting && baselines.resting.bpm != null) {
    const yy = y(baselines.resting.bpm);
    content += `<line x1="${left}" y1="${yy}" x2="${w - right}" y2="${yy}" stroke="#8fa0b3" stroke-dasharray="5 4" stroke-width="1"></line>`;
  }
  $a('analytics-baseline-chart').innerHTML = content;
  $a('analytics-baseline-legend').innerHTML = [
    '<span><i style="background:#ff7a45"></i>1 h mean</span>',
    '<span><i style="background:#f6bd16"></i>6 h mean</span>',
    '<span><i style="background:#61ddaa"></i>24 h mean</span>',
    '<span><i style="background:#5b8ff9"></i>7 d mean</span>',
    '<span><i style="background:#b37feb"></i>28 d mean</span>',
    '<span><i style="background:#8fa0b3"></i>Resting proxy</span>',
  ].join('');
}

function aRender(data) {
  A.data = data;
  aRenderSummary(data);
  aRenderTables();
  aRenderDistribution(data.distribution);
  aRenderBands(data.bands);
  aRenderSleep(data.sleep);
  aRenderHeatmap(data.heatmap);
  aRenderBaseline(data.baseline);
}

async function aRefresh() {
  if (A.loading) {
    // Keep the latest control value instead of dropping the change while a
    // request is already in flight (for example a bin-width change during the
    // 30-second refresh).
    A.refreshQueued = true;
    return;
  }
  A.loading = true;
  A.refreshQueued = false;
  $a('analytics-refresh').disabled = true;
  try {
    const params = new URLSearchParams({ range: A.range, bin_width: A.binWidth });
    if (A.bands) params.set('bands', A.bands);
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
    if (A.refreshQueued) {
      A.refreshQueued = false;
      aRefresh();
    }
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
$a('analytics-bin-width').addEventListener('change', () => {
  A.binWidth = parseFloat($a('analytics-bin-width').value) || 5;
  aRefresh();
});
$a('analytics-bands-apply').onclick = () => {
  A.bands = $a('analytics-bands-input').value.trim();
  aRefresh();
};
$a('analytics-bands-reset').onclick = () => {
  A.bands = '';
  $a('analytics-bands-input').value = DEFAULT_BANDS_TEXT;
  aRefresh();
};
$a('analytics-heatmap-metric').addEventListener('change', () => {
  A.heatmapMetric = $a('analytics-heatmap-metric').value;
  if (A.data) aRenderHeatmap(A.data.heatmap);
});

(function aInit() {
  const now = new Date();
  $a('analytics-start').value = toIstInput(new Date(now.getTime() - 24 * 3600 * 1000).toISOString());
  $a('analytics-end').value = toIstInput(now.toISOString());
  $a('analytics-bands-input').value = DEFAULT_BANDS_TEXT;
  aRefresh();
  setInterval(aRefresh, 30000);
})();
</script>
</body>
</html>
"""
