/*
 * Write one pre-encrypted FE86 frame through the existing authenticated GATT.
 *
 * This does not hook notifications and does not touch the app's callback; use
 * scripts/frida_trackb_capture.js in a separate session to record the replies.
 * Hooking onCharacteristicChanged in a second injector crashed :PhoneService
 * on 2026-11-25, so this script deliberately stays write-only.
 *
 * Edit FRAME_HEX (the complete LP frame, including 5A header and CRC), then:
 *   frida -U -p <PhoneService pid> -l scripts/frida_write_fe86.js
 */

'use strict';

const FRAME_HEX = '';

Java.perform(function () {
  if (!FRAME_HEX) {
    send({ kind: 'error', message: 'set FRAME_HEX first' });
    return;
  }
  const UUID = Java.use('java.util.UUID');
  const svcU = UUID.fromString('0000fe86-0000-1000-8000-00805f9b34fb');
  const chU = UUID.fromString('0000fe01-0000-1000-8000-00805f9b34fb');
  const bytes = Java.array(
    'byte',
    FRAME_HEX.match(/../g).map(function (h) { return parseInt(h, 16); })
  );

  let done = false;
  Java.choose('android.bluetooth.BluetoothGatt', {
    onMatch: function (gatt) {
      if (done) return;
      try {
        const service = gatt.getService(svcU);
        if (!service) return;
        const characteristic = service.getCharacteristic(chU);
        if (!characteristic) return;
        characteristic.setValue(bytes);
        const ok = gatt.writeCharacteristic(characteristic);
        send({ kind: 'write', ok: ok });
        done = true;
      } catch (e) {
        send({ kind: 'error', message: String(e) });
      }
    },
    onComplete: function () {
      if (!done) send({ kind: 'error', message: 'FE86 GATT not found' });
    }
  });
});
