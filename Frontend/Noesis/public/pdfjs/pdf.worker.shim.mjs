// Installs Map.prototype.getOrInsertComputed (see src/app/shared/ui/pdfjs-compat.ts) inside the
// PDF.js worker scope, then starts the real worker. The import is dynamic so the polyfill is in
// place before any of the worker's own code runs.
for (const ctor of [Map, WeakMap]) {
  if (typeof ctor.prototype.getOrInsertComputed === 'function') continue;
  Object.defineProperty(ctor.prototype, 'getOrInsertComputed', {
    configurable: true,
    writable: true,
    value(key, callbackfn) {
      if (this.has(key)) return this.get(key);
      const value = callbackfn(key);
      this.set(key, value);
      return value;
    },
  });
}

await import('./pdf.worker.min.mjs');
