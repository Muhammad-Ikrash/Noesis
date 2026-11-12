import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

// 24px stroke icons, drawn to match the thin-rule aesthetic.
const PATHS: Record<string, string> = {
  upload: 'M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
  trash: 'M4 7h16M10 11v6m4-6v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3',
  book: 'M4 5a1 1 0 0 1 1-1h5a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H5a1 1 0 0 1-1-1zm16 0a1 1 0 0 0-1-1h-5a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h5a1 1 0 0 0 1-1z',
  chat: 'M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9l-4 4V6a1 1 0 0 1 1-1z',
  quiz: 'M9 9a3 3 0 1 1 4 2.8c-.6.3-1 .9-1 1.6V14m0 3.5v.5M4 4h16v16H4z',
  plus: 'M12 5v14M5 12h14',
  sun: 'M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7 1.4-1.4M4.9 19.1l1.4-1.4m0-11.4L4.9 4.9m14.2 14.2-1.4-1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5',
  monitor: 'M4 5h16v11H4zM9 20h6m-3-4v4',
  x: 'M6 6l12 12M18 6 6 18',
  left: 'm15 6-6 6 6 6',
  right: 'm9 6 6 6-6 6',
  'zoom-in': 'M11 8v6m-3-3h6m6 9-4.3-4.3M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  'zoom-out': 'M8 11h6m6 9-4.3-4.3M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  send: 'M5 12h13m0 0-5-5m5 5-5 5',
  clip: 'm20 11-8.5 8.5a5 5 0 0 1-7-7L13 4a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L14.5 7',
  file: 'M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7zm0 0v4h4',
  arrow: 'M5 12h14m0 0-6-6m6 6-6 6',
  panel: 'M4 5h16v14H4zM9 5v14',
  check: 'm5 12 5 5 9-10',
  refresh: 'M20 11a8 8 0 0 0-14.8-4M4 4v4h4m-4 5a8 8 0 0 0 14.8 4M20 20v-4h-4',
  library: 'M5 4v16M9 4v16M13 5l4 15M19 20',
  edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
};

@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true', style: 'display:inline-flex;flex:none' },
  template: `<svg [attr.width]="size()" [attr.height]="size()" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path [attr.d]="d()" /></svg>`,
})
export class Icon {
  readonly name = input.required<string>();
  readonly size = input(18);
  protected readonly d = computed(() => PATHS[this.name()] ?? '');
}
