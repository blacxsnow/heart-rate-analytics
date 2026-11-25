'use strict';

Java.perform(function () {
  send({ kind: 'start', pid: Process.id });
  try {
    const loaded = Java.enumerateLoadedClassesSync();
    const matches = loaded.filter(function (n) {
      return /(^|\.)djr$|(^|\.)djp$|hichain|hwbtsdk|deviceauth/i.test(n);
    });
    send({ kind: 'loaded-matches', count: matches.length, matches: matches.slice(0, 200) });
  } catch (e) {
    send({ kind: 'loaded-error', error: String(e) });
  }
  try {
    const loaders = Java.enumerateClassLoadersSync();
    send({ kind: 'loaders', count: loaders.length });
    loaders.forEach(function (loader, i) {
      ['o.djr', 'o.djp', 'com.huawei.hwbtsdk.hichain.HiChainAuthManager'].forEach(function (cn) {
        try {
          loader.loadClass(cn);
          send({ kind: 'found', cls: cn, loader: i, loaderStr: String(loader) });
        } catch (e) { /* not this loader */ }
      });
    });
  } catch (e) {
    send({ kind: 'loaders-error', error: String(e) });
  }
});
