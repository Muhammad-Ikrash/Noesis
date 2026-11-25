/**
 * PDF.js 5.x calls Map.prototype.getOrInsertComputed (a stage-3 proposal) and ships no fallback,
 * so every page render throws on engines that lack it — Firefox as of 2026. Install it before
 * loading PDF.js, on the main thread and inside the worker (public/pdfjs/pdf.worker.shim.mjs).
 */
export function installMapGetOrInsertComputed(): void {
  for (const ctor of [Map, WeakMap]) {
    const proto = ctor.prototype as { getOrInsertComputed?: unknown };
    if (typeof proto.getOrInsertComputed === 'function') continue;
    Object.defineProperty(proto, 'getOrInsertComputed', {
      configurable: true,
      writable: true,
      value: function (this: Map<unknown, unknown>, key: unknown, callbackfn: (key: unknown) => unknown) {
        if (this.has(key)) return this.get(key);
        const value = callbackfn(key);
        this.set(key, value);
        return value;
      },
    });
  }
}
