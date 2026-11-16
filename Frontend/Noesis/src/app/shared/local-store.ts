/**
 * Small, failure-tolerant wrapper around localStorage for per-browser conveniences
 * (quiz drafts, last-read page). Every call swallows errors so pages still work when
 * storage is disabled, full, or unavailable (private windows, blocked site data).
 */

const PREFIX = 'noesis.';

export function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? null : (JSON.parse(raw) as T);
  } catch {
    return null;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage unavailable or full: the feature degrades silently.
  }
}

export function removeKey(key: string): void {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    // Ignore.
  }
}
