/*
 * Packer-independent crypto observer.
 *
 * Hooks javax.crypto.Cipher / SecretKeySpec / IvParameterSpec to capture the
 * key, IV, plaintext and ciphertext used by Huawei Health's TLV encryption.
 * Read-only.
 */

'use strict';

const T0 = Date.now();
function now() { return ((Date.now() - T0) / 1000).toFixed(3); }
function emit(kind, fields) { send(Object.assign({ t: now(), kind: kind }, fields)); }

function hex(v) {
  if (v === null || v === undefined) return null;
  try {
    if (v instanceof ArrayBuffer) v = new Uint8Array(v);
    if (typeof v.length !== 'number') return String(v);
    let s = '';
    for (let i = 0; i < v.length; i++) {
      const b = v[i] & 0xff;
      s += (b < 16 ? '0' : '') + b.toString(16);
    }
    return s;
  } catch (e) { return '<err>'; }
}

function keyInfo(k) {
  if (!k) return null;
  try {
    return { alg: k.getAlgorithm(), key_hex: hex(k.getEncoded()) };
  } catch (e) { return { error: String(e) }; }
}

Java.perform(function () {
  emit('session.start', { pid: Process.id });

  try {
    const SK = Java.use('javax.crypto.spec.SecretKeySpec');
    SK.$init.overloads.forEach(function (ov, i) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        emit('SecretKeySpec', {
          overload: i,
          argTypes: ov.argumentTypes.map(function (t) { return t.className; }),
          key_hex: hex(args[0]),
          algorithm: args.length > 1 ? String(args[args.length - 1]) : null
        });
        return ov.apply(this, args);
      };
    });
    emit('hook.ok', { cls: 'javax.crypto.spec.SecretKeySpec' });
  } catch (e) { emit('hook.miss', { cls: 'SecretKeySpec', error: String(e) }); }

  try {
    const IV = Java.use('javax.crypto.spec.IvParameterSpec');
    IV.$init.overloads.forEach(function (ov, i) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        emit('IvParameterSpec', { overload: i, iv_hex: hex(args[0]) });
        return ov.apply(this, args);
      };
    });
    emit('hook.ok', { cls: 'javax.crypto.spec.IvParameterSpec' });
  } catch (e) { emit('hook.miss', { cls: 'IvParameterSpec', error: String(e) }); }

  try {
    const Cipher = Java.use('javax.crypto.Cipher');
    Cipher.init.overloads.forEach(function (ov, i) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        const rec = {
          overload: i,
          argTypes: ov.argumentTypes.map(function (t) { return t.className; }),
          mode: args[0],
          key: keyInfo(args[1]),
          algorithm: null
        };
        try { rec.algorithm = this.getAlgorithm(); } catch (e) {}
        try {
          if (args[2] && args[2].getIV) rec.iv_hex = hex(args[2].getIV());
        } catch (e) {}
        emit('Cipher.init', rec);
        return ov.apply(this, args);
      };
    });
    Cipher.doFinal.overloads.forEach(function (ov, i) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        let input = null;
        if (args[0] && typeof args[0].length === 'number') input = hex(args[0]);
        let result;
        try { result = ov.apply(this, args); }
        catch (e) { emit('Cipher.doFinal.error', { overload: i, error: String(e) }); throw e; }
        emit('Cipher.doFinal', {
          overload: i,
          argTypes: ov.argumentTypes.map(function (t) { return t.className; }),
          algorithm: (function () { try { return this.getAlgorithm(); } catch (e) { return null; } }).call(this),
          input_hex: input,
          output_hex: hex(result),
          input_len: args[0] && args[0].length
        });
        return result;
      };
    });
    emit('hook.ok', { cls: 'javax.crypto.Cipher' });
  } catch (e) { emit('hook.miss', { cls: 'Cipher', error: String(e) }); }
});
