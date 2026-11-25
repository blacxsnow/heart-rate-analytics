/*
 * Track B capture (low overhead): GATT frames + AES-GCM plaintext.
 *
 * Huawei Health uses AES-GCM for the 0x7C/0x7D/0x7E TLV envelope and for
 * device JSON payloads. CBC is used for local storage and is intentionally
 * not logged, to avoid slowing the app into an ANR.
 *
 * Read-only. Attach to the running main process:
 *   frida -U -p <pid> -l scripts/frida_trackb_capture.js
 */

'use strict';

(function () {
  const T0 = Date.now();
  const hooked = new Set();

  function now() { return ((Date.now() - T0) / 1000).toFixed(3); }
  function emit(kind, fields) { send(Object.assign({ t: now(), kind: kind }, fields)); }

  function hex(v, max) {
    if (v === null || v === undefined) return null;
    try {
      if (v instanceof ArrayBuffer) v = new Uint8Array(v);
      if (typeof v.length !== 'number') return String(v);
      const n = Math.min(v.length, max || 4096);
      let s = '';
      for (let i = 0; i < n; i++) {
        const b = v[i] & 0xff;
        s += (b < 16 ? '0' : '') + b.toString(16);
      }
      return s + (v.length > n ? '..' : '');
    } catch (e) { return '<err>'; }
  }

  function uuidOf(obj) {
    try { return String(obj.getUuid()); } catch (e) { return null; }
  }

  function hookGatt() {
    let Gatt;
    try { Gatt = Java.use('android.bluetooth.BluetoothGatt'); }
    catch (e) { emit('hook.miss', { cls: 'BluetoothGatt' }); return; }

    Gatt.writeCharacteristic.overloads.forEach(function (ov, idx) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        let uuid = null, value = null;
        try { uuid = uuidOf(args[0]); value = hex(args[0].getValue()); } catch (e) {}
        emit('gatt.write', { uuid: uuid, value: value });
        return ov.apply(this, args);
      };
    });

    Gatt.writeDescriptor.overloads.forEach(function (ov, idx) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        let uuid = null, value = null;
        try { uuid = uuidOf(args[0]); value = hex(args[0].getValue()); } catch (e) {}
        emit('gatt.writeDescriptor', { uuid: uuid, value: value });
        return ov.apply(this, args);
      };
    });

    emit('hook.ok', { cls: 'BluetoothGatt' });
  }

  function hookCallbacks() {
    let names;
    try { names = Java.enumerateLoadedClassesSync(); } catch (e) { return; }
    names.forEach(function (name) {
      if (name.indexOf('GattCallback') === -1) return;
      let C;
      try { C = Java.use(name); } catch (e) { return; }
      if (!C.onCharacteristicChanged || !C.onCharacteristicChanged.overloads) return;
      C.onCharacteristicChanged.overloads.forEach(function (ov, idx) {
        const key = 'cb:' + name + '#' + idx;
        if (hooked.has(key)) return;
        hooked.add(key);
        ov.implementation = function () {
          const args = Array.prototype.slice.call(arguments);
          let uuid = null, value = null;
          try { uuid = uuidOf(args[1]); value = hex(args[2]); } catch (e) {}
          emit('gatt.notifyRx', { cls: name, uuid: uuid, value: value });
          return ov.apply(this, args);
        };
      });
    });
  }

  function hookGcm() {
    let Cipher;
    try { Cipher = Java.use('javax.crypto.Cipher'); }
    catch (e) { emit('hook.miss', { cls: 'Cipher' }); return; }

    Cipher.init.overloads.forEach(function (ov, idx) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        let alg = null;
        try { alg = String(this.getAlgorithm()); } catch (e) {}
        if (!alg || alg.indexOf('GCM') === -1) return ov.apply(this, args);
        let key = null, iv = null;
        try { key = hex(args[1].getEncoded(), 64); } catch (e) {}
        try { if (args[2] && args[2].getIV) iv = hex(args[2].getIV(), 32); } catch (e) {}
        emit('gcm.init', { algorithm: alg, key: key, iv: iv, mode: args[0] });
        return ov.apply(this, args);
      };
    });

    Cipher.doFinal.overloads.forEach(function (ov, idx) {
      ov.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        let alg = null;
        try { alg = String(this.getAlgorithm()); } catch (e) {}
        if (!alg || alg.indexOf('GCM') === -1) return ov.apply(this, args);
        let input = null;
        try { if (args[0] && typeof args[0].length === 'number') input = hex(args[0]); } catch (e) {}
        const result = ov.apply(this, args);
        emit('gcm.final', {
          algorithm: alg,
          input: input,
          inputLen: (function () { try { return args[0].length; } catch (e) { return null; } })(),
          output: hex(result),
          outputLen: (function () { try { return result.length; } catch (e) { return null; } })()
        });
        return result;
      };
    });

    emit('hook.ok', { cls: 'Cipher(AES/GCM)' });
  }

  Java.perform(function () {
    emit('session.start', { pid: Process.id, arch: Process.arch });
    hookGatt();
    hookGcm();
    hookCallbacks();
    setInterval(function () { hookCallbacks(); }, 5000);
  });
})();
