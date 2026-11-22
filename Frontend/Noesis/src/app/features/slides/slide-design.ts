import { SlideDesign, SlideFont, SlideTheme } from '../../core/api/models';

/** Same palettes as the PowerPoint export (backend services/slides_export.py). */
export const THEMES: { id: SlideTheme; label: string; bg: string; ink: string; accent: string }[] = [
  { id: 'auto', label: 'App', bg: '', ink: '', accent: '' },
  { id: 'paper', label: 'Paper', bg: '#f5f0e6', ink: '#1e1a15', accent: '#962f22' },
  { id: 'ink', label: 'Ink', bg: '#14161b', ink: '#ebe3d3', accent: '#e58466' },
  { id: 'slate', label: 'Slate', bg: '#f4f6f8', ink: '#1f2937', accent: '#2563eb' },
  { id: 'forest', label: 'Forest', bg: '#f2f5ef', ink: '#1d2b22', accent: '#2f6b45' },
  { id: 'midnight', label: 'Midnight', bg: '#0f172a', ink: '#e2e8f0', accent: '#38bdf8' },
];

export const FONT_LABELS: Record<SlideFont, string> = { serif: 'Serif', sans: 'Sans', mono: 'Mono' };

const FONT_STACKS: Record<SlideFont, string> = {
  serif: 'var(--font-read)',
  sans: 'var(--font-ui)',
  mono: 'var(--font-mono)',
};

export const DEFAULT_DESIGN: SlideDesign = {
  theme: 'auto',
  accent: null,
  heading_font: 'serif',
  body_font: 'sans',
  align: 'left',
  bullets: 'dot',
  show_numbers: true,
  show_sources: true,
};

/** CSS custom properties for a slide. "auto" leaves colours to the app's own theme tokens. */
export function designVars(d: SlideDesign): Record<string, string> {
  const theme = THEMES.find((t) => t.id === d.theme);
  const vars: Record<string, string> = {
    '--s-head': FONT_STACKS[d.heading_font],
    '--s-body': FONT_STACKS[d.body_font],
  };
  if (theme && theme.id !== 'auto') {
    vars['--s-bg'] = theme.bg;
    vars['--s-ink'] = theme.ink;
    vars['--s-accent'] = theme.accent;
  }
  if (d.accent) vars['--s-accent'] = d.accent;
  return vars;
}

/** How much text a slide carries, which sets its type size before any measured fit. */
export type SlideDensity = 'sparse' | 'normal' | 'dense' | 'tight';

/**
 * A few short bullets read better large; long lists need smaller type to stay inside 16:9.
 * The viewer still measures the slide afterwards and shrinks it further if text would be cut off.
 */
export function slideDensity(slide: { title: string; bullets: string[] }): SlideDensity {
  const bullets = slide.bullets.filter((b) => b.trim());
  const chars = bullets.reduce((n, b) => n + b.trim().length, 0) + Math.max(0, slide.title.length - 60);
  if (bullets.length <= 3 && chars <= 180) return 'sparse';
  if (bullets.length <= 5 && chars <= 420) return 'normal';
  if (bullets.length <= 7 && chars <= 650) return 'dense';
  return 'tight';
}

/** The accent shown in the colour picker: custom, theme, or the app's light-theme pen. */
export function effectiveAccent(d: SlideDesign): string {
  return d.accent ?? (THEMES.find((t) => t.id === d.theme)?.accent || '#962f22');
}
