/*
 * Frida observer for Huawei Health <-> Band 9 BLE traffic.
 *
 * Read-only: every hook calls the original implementation and only logs.
 * Usage:
 *   frida -U -f com.huawei.health -l scripts/frida_ble_hooks.js --no-pause
 *   frida -U -n "Huawei Health" -l scripts/frida_ble_hooks.js
 *
 * Output is JSON lines on the Frida console. Redirect with -o.
 */

'use strict';

const T0 = Date.now();
const hooked = new Set();

function now() {
  return ((Date.now() - T0) / 1000).toFixed(3);
}

function toHex(value) {
  if (value === null || value === undefined) return null;
  try {
    if (typeof value === 'string') return value;
    if (value instanceof ArrayBuffer) {
      value = new Uint8Array(value);
    }
    if (typeof value.length !== 'number') return String(value);
    let out = '';
    for (let i = 0; i < value.length; i++) {
      const b = value[i] & 0xff;
      out += (b < 16 ? '0' : '') + b.toString(16);
    }
    return out;
  } catch (e) {
    return '<unreadable:' + e + '>';
  }
}

function emit(kind, fields) {
  const record = Object.assign({ t: now(), kind: kind }, fields);
  send(record);
}

function safeUuid(obj) {
  try {
    return obj.getUuid().toString();
  } catch (e) {
    return null;
  }
}

function hookGatt() {
  try {
    const Gatt = Java.use('android.bluetooth.BluetoothGatt');

    Gatt.writeCharacteristic.overloads.forEach(function (overload) {
      overload.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        let uuid = null;
        let value = null;
        try {
          const ch = args[0];
          uuid = safeUuid(ch);
          value = toHex(ch.getValue());
        } catch (e) {}
        emit('gatt.writeCharacteristic', {
          uuid: uuid,
          value: value,
          argTypes: overload.argumentTypes.map(function (t) { return t.className; }),
          argsHex: args.map(function (a) { return toHex(a); })
        });
        return overload.apply(this, args);
      };
    });

    Gatt.writeDescriptor.overloads.forEach(function (overload) {
      overload.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        let uuid = null;
        let value = null;
        try {
          uuid = args[0].getUuid().toString();
          value = toHex(args[0].getValue());
        } catch (e) {}
        emit('gatt.writeDescriptor', { uuid: uuid, value: value });
        return overload.apply(this, args);
      };
    });

    Gatt.readCharacteristic.overloads.forEach(function (overload) {
      overload.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        emit('gatt.readCharacteristic', { uuid: safeUuid(args[0]) });
        return overload.apply(this, args);
      };
    });

    Gatt.setCharacteristicNotification.overloads.forEach(function (overload) {
      overload.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        emit('gatt.setCharacteristicNotification', {
          uuid: safeUuid(args[0]),
          enable: args[1]
        });
        return overload.apply(this, args);
      };
    });
  } catch (e) {
    emit('hook.error', { target: 'android.bluetooth.BluetoothGatt', error: String(e) });
  }
}

function hookClassMethods(className, methodNames) {
  let cls;
  try {
    cls = Java.use(className);
  } catch (e) {
    return false;
  }
  methodNames.forEach(function (name) {
    let method;
    try {
      method = cls[name];
    } catch (e) {
      return;
    }
    if (!method || !method.overloads) return;
    method.overloads.forEach(function (overload, index) {
      const key = className + '.' + name + '#' + index;
      if (hooked.has(key)) return;
      hooked.add(key);
      overload.implementation = function () {
        const args = Array.prototype.slice.call(arguments);
        emit('huawei.method', {
          cls: className,
          method: name,
          overload: index,
          argTypes: overload.argumentTypes.map(function (t) { return t.className; }),
          argsHex: args.map(function (a) { return toHex(a); })
        });
        return overload.apply(this, args);
      };
    });
  });
  return true;
}

function hookHuawei() {
  // GATT client used by Huawei Health for FE86/FE01/FE02.
  hookClassMethods('o.djr', ['b', 'e', 'i', 'k']);

  // Command queue / encryption / slicing.
  hookClassMethods('o.djp', ['e', 'c', 'a', 'k']);

  // Handshake packet builder and TLV encryption wrapper.
  hookClassMethods('o.dig', ['c', 'e', 'a']);

  // AES/HMAC helpers.
  hookClassMethods('o.dip', ['a', 'b', 'c']);

  // HiChain Lite TLV codec.
  hookClassMethods('o.dkc', ['c', 'd', 'e']);

  // App-side HiChain manager.
  hookClassMethods('com.huawei.hwbtsdk.hichain.HiChainAuthManager', [
    'c', 'a', 'd', 'e', 'q', 's', 't', 'bindPeer', 'authenticatePeer'
  ]);

  // Platform HiChain SDK (may be in a separate APK/module).
  hookClassMethods('com.huawei.security.deviceauth.HwDeviceAuthManager', [
    'bindPeer', 'authenticatePeer', 'processReceivedData', 'registerNewUser'
  ]);
}

function hookGattCallbacks() {
  // Enumerate loaded classes and hook onCharacteristicChanged on any callback
  // subclass. This is best-effort; HCI logging remains the source of truth.
  try {
    const names = Java.enumerateLoadedClassesSync();
    names.forEach(function (name) {
      if (name.indexOf('BluetoothGattCallback') === -1 && name.indexOf('GattCallback') === -1) return;
      try {
        const cls = Java.use(name);
        if (cls.onCharacteristicChanged && cls.onCharacteristicChanged.overloads) {
          cls.onCharacteristicChanged.overloads.forEach(function (overload, idx) {
            const key = 'cb:' + name + '#' + idx;
            if (hooked.has(key)) return;
            hooked.add(key);
            overload.implementation = function () {
              const args = Array.prototype.slice.call(arguments);
              let uuid = null;
              let value = null;
              try {
                uuid = safeUuid(args[1]);
                value = toHex(args[2]);
              } catch (e) {}
              emit('callback.onCharacteristicChanged', {
                cls: name,
                uuid: uuid,
                value: value,
                argsHex: args.map(function (a) { return toHex(a); })
              });
              return overload.apply(this, args);
            };
          });
        }
      } catch (e) {}
    });
  } catch (e) {
    emit('hook.error', { target: 'gatt-callbacks', error: String(e) });
  }
}

Java.perform(function () {
  emit('session.start', { pid: Process.id, arch: Process.arch });
  hookGatt();
  hookHuawei();
  hookGattCallbacks();

  // Classes may be loaded later (Huawei Health uses dynamic modules).
  setTimeout(function () {
    hookHuawei();
    hookGattCallbacks();
  }, 5000);
  setTimeout(function () {
    hookHuawei();
    hookGattCallbacks();
  }, 20000);
});
