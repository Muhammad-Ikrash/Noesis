export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

export const STATUS_LABEL: Record<string, string> = {
  pending: 'queued',
  processing: 'reading',
  completed: 'ready',
  failed: 'failed',
  missing: 'file missing',
};

export function statusClass(status: string): string {
  return {
    pending: 'pill--warn pill--busy',
    processing: 'pill--warn pill--busy',
    completed: 'pill--ok',
    failed: 'pill--danger',
    missing: 'pill--danger',
  }[status] ?? '';
}
