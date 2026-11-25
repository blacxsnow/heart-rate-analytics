/*
 * OTA inspection observer for Huawei Health (current implementation).
 *
 * Read-only: logs the firmware version-check request body and response, plus
 * download URLs. Does not modify the request, install, or write to the band.
 *
 * Runtime classes (Huawei Health 11.0.0.517):
 *   mkl  - version check util (build request / post / parse)
 *   mkp  - check thread (Runnable)
 *   kka  - HTTPS post helper
 *
 * The observer never rewrites the request. To retrieve the package we replay
 * the captured JSON check offline with a previous version string.
 */

'use strict';

const T0 = Date.now();
const hooked = new Set();

function now() { return ((Date.now() - T0) / 1000).toFixed(3); }
function emit(kind, fields) { send(Object.assign({ t: now(), kind: kind }, fields)); }

function text(v, max) {
  if (v === null || v === undefined) return null;
  try { return String(v).slice(0, max || 8192); } catch (e) { return '<err>'; }
}

function looksJson(s) {
  if (typeof s !== 'string') return false;
  const t = s.trim();
  return t.length > 1 && (t[0] === '{' || t[0] === '[');
}

function logString(s, max) {
  if (looksJson(s)) return text(s, max || 12000);
  return text(s, 300);
}

function hookClass(className, methodNames, opts) {
  opts = opts || {};
  let C;
  try { C = Java.use(className); }
  catch (e) { if (opts.quiet !== true) emit('hook.miss', { cls: className }); return false; }
  if (!opts.quiet) emit('hook.ok', { cls: className });
  methodNames.forEach(function (name) {
    let m;
    try { m = C[name]; } catch (e) { return; }
    if (!m || !m.overloads) return;
    m.overloads.forEach(function (ov, idx) {
      const key = className + '.' + name + '#' + idx;
      if (hooked.has(key)) return;
      hooked.add(key);
      const types = ov.argumentTypes.map(function (t) { return t.className; });
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        const rec = {
          cls: className, method: name, overload: idx, argTypes: types,
          args: args.map(function (a, i) {
            if (a === null || a === undefined) return null;
            if (types[i] === 'java.lang.String') return logString(String(a));
            if (types[i] === '[B') return text(a, 200);
            return text(a, 160);
          })
        };
        let result;
        try { result = ov.apply(this, args); }
        catch (e) { emit('call.error', Object.assign(rec, { error: String(e) })); throw e; }
        if (typeof result === 'string') rec.ret = logString(String(result), 16000);
        else if (result !== null && result !== undefined) rec.ret = text(result, 160);
        emit('call', rec);
        return result;
      };
    });
  });
  return true;
}

function hookAll() {
  // Version check util.
  hookClass('mkl', ['a', 'b', 'c', 'd', 'e'], { quiet: true });
  // Check thread.
  hookClass('mkp', ['run', 'c', 'bZg_', 'a'], { quiet: true });
  // HTTPS helper (body + response).
  hookClass('kka', ['c', 'e'], { quiet: true });
}

Java.perform(function () {
  emit('session.start', { pid: Process.id, arch: Process.arch });
  hookAll();
  setInterval(hookAll, 3000);
});
