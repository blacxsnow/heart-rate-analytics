/*
 * Targeted plaintext/session-key observer for Huawei Health.
 *
 * Goal: capture the TLV payload *before* it is encrypted, plus the HiChain
 * session key, so the independent client can reproduce the protocol.
 *
 * Read-only. Attach to the process that owns BLE (usually :PhoneService).
 */

'use strict';

const T0 = Date.now();
const hooked = new Set();

function now() { return ((Date.now() - T0) / 1000).toFixed(3); }
function sendEvent(kind, fields) { send(Object.assign({ t: now(), kind: kind }, fields)); }

function hex(v) {
  if (v === null || v === undefined) return null;
  try {
    if (typeof v === 'string') return v;
    if (v instanceof ArrayBuffer) v = new Uint8Array(v);
    if (typeof v.length !== 'number') return String(v);
    let s = '';
    for (let i = 0; i < v.length; i++) {
      const b = v[i] & 0xff;
      s += (b < 16 ? '0' : '') + b.toString(16);
    }
    return s;
  } catch (e) { return '<err:' + e + '>'; }
}

function describeArg(a, typeName) {
  if (a === null || a === undefined) return null;
  if (typeName === '[B' || (typeName && typeName.indexOf('byte[]') >= 0)) return { hex: hex(a) };
  if (typeName === 'java.lang.String') return String(a);
  if (typeName === 'int' || typeName === 'long' || typeName === 'short' || typeName === 'byte' || typeName === 'boolean') return a;
  return { obj: String(a) };
}

function describeDji(obj) {
  try {
    return {
      service: obj.e(),
      command: obj.c(),
      len: obj.f(),
      needEncrypt: obj.k(),
      data_hex: hex(obj.d())
    };
  } catch (e) { return { error: String(e) }; }
}

function hookClass(className, methodNames, filter) {
  let C;
  try { C = Java.use(className); }
  catch (e) { sendEvent('hook.miss', { cls: className, error: String(e) }); return; }
  sendEvent('hook.ok', { cls: className });
  methodNames.forEach(function (name) {
    let m;
    try { m = C[name]; } catch (e) { return; }
    if (!m || !m.overloads) return;
    m.overloads.forEach(function (ov, idx) {
      const key = className + '.' + name + '#' + idx;
      if (hooked.has(key)) return;
      hooked.add(key);
      const types = ov.argumentTypes.map(function (t) { return t.className; });
      if (filter && !filter(types)) return;
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        const fields = { cls: className, method: name, overload: idx, argTypes: types };
        if (args[0] && types[0] === 'o.dji') fields.dji = describeDji(args[0]);
        fields.args = args.map(function (a, i) { return describeArg(a, types[i]); });
        sendEvent('call', fields);
        return ov.apply(this, args);
      };
    });
  });
}

function hookHiChain() {
  // The callback that receives the negotiated session key.
  hookClass('com.huawei.hwbtsdk.hichain.HiChainAuthManager$HichainCallbackHandler', [
    'onSessionKeyReturned', 'onDataTransmit', 'onOperationFinished', 'onReceiveRequest'
  ]);
  hookClass('com.huawei.hwbtsdk.hichain.HiChainAuthManager', [
    'c', 'a', 'd', 'e', 'q', 's', 't'
  ]);
  hookClass('com.huawei.security.deviceauth.HwDeviceAuthManager', [
    'bindPeer', 'authenticatePeer', 'processReceivedData', 'registerNewUser'
  ]);
  hookClass('com.huawei.security.deviceauth.HwDevAuthCallback', [
    'onSessionKeyReturned', 'onDataTransmit', 'onOperationFinished', 'onReceiveRequest'
  ]);
}

function hookTransport() {
  // Log plaintext command objects and byte[] payloads before encryption.
  hookClass('o.djp', ['c', 'e', 'a', 'k']);
  hookClass('o.dig', ['c', 'e', 'a']);
  hookClass('o.dip', ['a', 'b', 'c']);
  hookClass('o.dkc', ['c', 'd', 'e']);
  hookClass('o.djr', ['b', 'e', 'i', 'k']);
}

Java.perform(function () {
  sendEvent('session.start', { pid: Process.id, arch: Process.arch });
  hookHiChain();
  hookTransport();
  setTimeout(function () { hookHiChain(); hookTransport(); }, 5000);
  setTimeout(function () { hookHiChain(); hookTransport(); }, 15000);
});
