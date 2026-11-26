import {
  ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, effect, inject, input, signal, untracked, viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { concatMap } from 'rxjs';
import { Slide, SlideDeck, SlideDesign, SlideFont, SlideSource, SlideTheme } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { SlidesService } from '../../core/services/slides.service';
import { ToastService } from '../../core/services/toast.service';
import { Icon } from '../../shared/ui/icon';
import { DEFAULT_DESIGN, FONT_LABELS, THEMES, designVars, effectiveAccent, slideDensity } from './slide-design';
import { ReviseDialog, ReviseRequest } from './revise-dialog';
import { downloadDeck } from './slides-download';

/** One citation per file: "a.pdf p. 3, 7" with a link to the first page. */
interface Cite {
  documentId: string | null;
  filename: string;
  pages: number[];
}

type Panel = 'none' | 'design' | 'edit';
type SaveState = 'idle' | 'saving' | 'saved' | 'error';

const SAVE_DELAY_MS = 600;
/** Smallest scale the auto-fit will shrink slide text to before letting it clip. */
const MIN_FIT = 0.6;
const MAX_SLIDES = 40;

@Component({
  selector: 'app-slides-viewer-page',
  imports: [RouterLink, Icon, ReviseDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown)': 'onKey($event)', '(document:fullscreenchange)': 'onFullscreenChange()' },
  templateUrl: './slides-viewer-page.html',
  // Slide and layout styles, the thumbnail strip, then the Design / Edit side panels.
  styleUrls: ['./slides-viewer-page.scss', './slides-viewer-strip.scss', './slides-viewer-panels.scss'],
})
export class SlidesViewerPage {
  readonly deckId = input.required<string>();

  private readonly api = inject(SlidesService);
  private readonly toast = inject(ToastService);
  private readonly stageEl = viewChild<ElementRef<HTMLElement>>('stage');
  private readonly stripEl = viewChild<ElementRef<HTMLElement>>('strip');
  private readonly reviseDlg = viewChild(ReviseDialog);

  protected readonly themes = THEMES;
  protected readonly fonts: SlideFont[] = ['serif', 'sans', 'mono'];
  protected readonly fontLabels = FONT_LABELS;

  protected readonly deck = signal<SlideDeck | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  /** 0 is the title slide; 1..n are the content slides. */
  protected readonly index = signal(0);
  protected readonly presenting = signal(false);
  protected readonly downloading = signal(false);
  protected readonly panel = signal<Panel>('none');

  protected readonly saveState = signal<SaveState>('idle');

  protected readonly reviseOpen = signal(false);
  protected readonly revising = signal(false);
  protected readonly reviseError = signal<string | null>(null);
  /** The deck as it was before the last AI revision, until the next manual change. */
  protected readonly undoSnapshot = signal<SlideDeck | null>(null);
  protected readonly undoing = signal(false);
  private slidesDirty = false;
  private metaDirty = false;
  private saveTimer: ReturnType<typeof setTimeout> | undefined;
  private saving = false;
  /** Raw bullet text per slide while editing, so blank lines survive typing. */
  private readonly bulletDrafts = new Map<string, string>();

  protected readonly design = computed<SlideDesign>(() => ({ ...DEFAULT_DESIGN, ...(this.deck()?.design ?? {}) }));
  protected readonly vars = computed(() => designVars(this.design()));
  protected readonly accent = computed(() => effectiveAccent(this.design()));
  protected readonly total = computed(() => (this.deck()?.slides.length ?? 0) + 1);
  protected readonly current = computed<Slide | null>(() => this.deck()?.slides[this.index() - 1] ?? null);
  protected readonly density = computed(() => {
    const s = this.current();
    return s ? slideDensity(s) : 'normal';
  });
  protected readonly filenames = computed(() => [
    ...new Set((this.deck()?.slides ?? []).flatMap((s) => s.sources.map((x) => x.filename))),
  ]);

  constructor() {
    effect(() => {
      this.deckId();
      untracked(() => this.load());
    });
    // Keep the active thumbnail in view while stepping through the deck. Only the strip
    // scrolls; scrollIntoView would also move the page.
    effect(() => {
      const i = this.index();
      const strip = this.stripEl()?.nativeElement;
      const thumb = strip?.querySelector<HTMLElement>(`[data-i="${i}"]`);
      if (!strip || !thumb) return;
      const left = thumb.offsetLeft - strip.offsetLeft;
      if (left < strip.scrollLeft) strip.scrollLeft = left;
      else if (left + thumb.offsetWidth > strip.scrollLeft + strip.clientWidth) {
        strip.scrollLeft = left + thumb.offsetWidth - strip.clientWidth;
      }
    });
    // Shrink the slide's text until nothing overflows the 16:9 frame (like "shrink text on
    // overflow" in PowerPoint). Runs after every change to what or how the slide shows.
    effect(() => {
      this.current();
      this.index();
      this.design();
      this.presenting();
      this.panel();
      const stage = this.stageEl()?.nativeElement;
      if (stage) untracked(() => this.scheduleFit(stage));
    });
    const onResize = () => {
      const stage = this.stageEl()?.nativeElement;
      if (stage) this.scheduleFit(stage);
    };
    window.addEventListener('resize', onResize);

    inject(DestroyRef).onDestroy(() => {
      window.removeEventListener('resize', onResize);
      cancelAnimationFrame(this.fitFrame);
      this.flushSave();
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    });
  }

  private fitFrame = 0;

  /** Waits a frame so the new slide is laid out, then fits it. */
  private scheduleFit(stage: HTMLElement): void {
    cancelAnimationFrame(this.fitFrame);
    this.fitFrame = requestAnimationFrame(() => {
      const slide = stage.querySelector<HTMLElement>('.slide');
      if (slide) fitSlide(slide);
    });
  }

  /** Width of a thumbnail's placeholder line, roughly following the bullet's length. */
  protected lineWidth(bullet: string): number {
    return Math.min(92, 38 + bullet.length * 0.5);
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.get(this.deckId()).subscribe({
      next: (d) => {
        this.deck.set(d);
        this.index.set(0);
        this.bulletDrafts.clear();
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiErrorMessage(e, 'This slide deck could not be loaded.'));
        this.loading.set(false);
      },
    });
  }

  protected go(i: number): void {
    this.index.set(Math.min(Math.max(i, 0), this.total() - 1));
  }

  protected togglePanel(p: Panel): void {
    this.panel.update((cur) => (cur === p ? 'none' : p));
  }

  protected cites(sources: SlideSource[]): Cite[] {
    const byFile = new Map<string, Cite>();
    for (const s of sources) {
      const c = byFile.get(s.filename) ?? { documentId: s.document_id, filename: s.filename, pages: [] };
      if (!c.pages.includes(s.page_number)) c.pages.push(s.page_number);
      byFile.set(s.filename, c);
    }
    return [...byFile.values()].map((c) => ({ ...c, pages: c.pages.sort((a, b) => a - b) }));
  }

  protected num(n: number): string {
    return n < 10 ? `0${n}` : `${n}`;
  }

  // ---- Design ---------------------------------------------------------------

  protected setDesign(patch: Partial<SlideDesign>): void {
    this.patchDeck((d) => ({ ...d, design: { ...this.design(), ...patch } }));
    this.markDirty('meta');
  }

  protected pickTheme(theme: SlideTheme): void {
    // A new theme brings its own accent; a custom accent is cleared.
    this.setDesign({ theme, accent: null });
  }

  protected resetDesign(): void {
    this.patchDeck((d) => ({ ...d, design: { ...DEFAULT_DESIGN } }));
    this.markDirty('meta');
  }

  // ---- Editing --------------------------------------------------------------

  protected setDeckTitle(value: string): void {
    this.patchDeck((d) => ({ ...d, title: value }));
    this.markDirty('meta');
  }

  protected setSubtitle(value: string): void {
    this.patchDeck((d) => ({ ...d, subtitle: value }));
    this.markDirty('meta');
  }

  protected bulletText(s: Slide): string {
    return this.bulletDrafts.get(s.id) ?? s.bullets.join('\n');
  }

  protected editSlide(id: string, patch: Partial<Pick<Slide, 'title' | 'notes'>>): void {
    this.updateSlides((slides) => slides.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  protected editBullets(id: string, text: string): void {
    this.bulletDrafts.set(id, text);
    const bullets = text.split('\n').map((b) => b.replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 10);
    this.updateSlides((slides) => slides.map((s) => (s.id === id ? { ...s, bullets } : s)));
  }

  /** Move the current slide by one place; the view follows it. */
  protected moveSlide(delta: number): void {
    const from = this.index() - 1;
    const to = from + delta;
    const slides = this.deck()?.slides ?? [];
    if (from < 0 || to < 0 || to >= slides.length) return;
    this.updateSlides((list) => {
      const next = [...list];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
    this.index.set(to + 1);
  }

  protected addSlide(): void {
    if ((this.deck()?.slides.length ?? 0) >= MAX_SLIDES) {
      this.toast.info(`A deck can have at most ${MAX_SLIDES} slides.`);
      return;
    }
    const at = this.index(); // insert after the current slide (or first, from the title slide)
    const slide: Slide = { id: crypto.randomUUID(), position: 0, title: 'New slide', bullets: ['First point'], notes: '', sources: [] };
    this.updateSlides((list) => [...list.slice(0, at), slide, ...list.slice(at)]);
    this.index.set(at + 1);
  }

  protected duplicateSlide(): void {
    const cur = this.current();
    if (!cur) return;
    if ((this.deck()?.slides.length ?? 0) >= MAX_SLIDES) {
      this.toast.info(`A deck can have at most ${MAX_SLIDES} slides.`);
      return;
    }
    const at = this.index();
    // The copy has no citations of its own: it is new content once edited.
    const copy: Slide = { ...cur, id: crypto.randomUUID(), sources: [] };
    this.updateSlides((list) => [...list.slice(0, at), copy, ...list.slice(at)]);
    this.index.set(at + 1);
  }

  protected deleteSlide(): void {
    const cur = this.current();
    const slides = this.deck()?.slides ?? [];
    if (!cur) return;
    if (slides.length <= 1) {
      this.toast.info('A deck needs at least one content slide.');
      return;
    }
    this.bulletDrafts.delete(cur.id);
    this.updateSlides((list) => list.filter((s) => s.id !== cur.id));
    this.index.set(Math.min(this.index(), slides.length - 1));
    this.toast.ok('Slide deleted.');
  }

  private updateSlides(fn: (slides: Slide[]) => Slide[]): void {
    this.patchDeck((d) => ({ ...d, slides: fn(d.slides).map((s, i) => ({ ...s, position: i + 1 })) }));
    this.markDirty('slides');
  }

  private patchDeck(fn: (d: SlideDeck) => SlideDeck): void {
    this.deck.update((d) => (d ? fn(d) : d));
  }

  // ---- Saving: debounced, the local deck stays the source of truth -----------

  private markDirty(kind: 'meta' | 'slides'): void {
    // A manual change after an AI revision becomes the new baseline: no undo across it.
    this.undoSnapshot.set(null);
    if (kind === 'meta') this.metaDirty = true;
    else this.slidesDirty = true;
    this.saveState.set('saving');
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.flushSave(), SAVE_DELAY_MS);
  }

  protected flushSave(): void {
    clearTimeout(this.saveTimer);
    const d = this.deck();
    if (!d || this.saving || (!this.metaDirty && !this.slidesDirty)) return;
    const meta = this.metaDirty;
    const slides = this.slidesDirty;
    this.metaDirty = this.slidesDirty = false;
    this.saving = true;
    this.saveState.set('saving');

    let pending = (meta ? 1 : 0) + (slides ? 1 : 0);
    let failed = false;
    const done = (ok: boolean, retryMeta: boolean, retrySlides: boolean) => (e?: unknown) => {
      if (!ok) {
        failed = true;
        if (retryMeta) this.metaDirty = true;
        if (retrySlides) this.slidesDirty = true;
        this.toast.error(apiErrorMessage(e, 'Your changes could not be saved.'));
      }
      if (--pending > 0) return;
      this.saving = false;
      if (failed) this.saveState.set('error');
      else if (this.metaDirty || this.slidesDirty) this.markDirty(this.slidesDirty ? 'slides' : 'meta');
      else this.saveState.set('saved');
    };

    if (meta) {
      this.api
        .update(d.id, { title: d.title.trim() || 'Untitled deck', subtitle: d.subtitle?.trim() || null, design: this.design() })
        .subscribe({ next: () => done(true, true, false)(), error: (e) => done(false, true, false)(e) });
    }
    if (slides) {
      const body = d.slides.map((s) => ({
        id: s.id,
        title: s.title.trim() || 'Untitled slide',
        bullets: s.bullets,
        notes: s.notes,
      }));
      this.api
        .replaceSlides(d.id, body)
        .subscribe({ next: () => done(true, false, true)(), error: (e) => done(false, false, true)(e) });
    }
  }

  // ---- Revise with AI -------------------------------------------------------

  protected openRevise(): void {
    this.reviseError.set(null);
    this.reviseOpen.set(true);
  }

  protected closeRevise(): void {
    if (!this.revising()) this.reviseOpen.set(false);
  }

  protected onRevise(req: ReviseRequest): void {
    const d = this.deck();
    if (!d || this.revising()) return;
    const slide = req.scope === 'slide' ? this.current() : null;
    this.revising.set(true);
    this.reviseError.set(null);
    this.flushSave();
    const snapshot = structuredClone(d);
    const run = () =>
      this.api.revise(d.id, req.instruction, slide?.id).subscribe({
        next: (fresh) => {
          this.deck.set(fresh);
          this.bulletDrafts.clear();
          this.index.set(Math.min(this.index(), fresh.slides.length));
          this.revising.set(false);
          this.reviseOpen.set(false);
          this.reviseDlg()?.clear();
          this.undoSnapshot.set(snapshot);
          this.saveState.set('saved');
          this.toast.ok(slide ? 'Slide revised.' : 'Deck revised.');
        },
        error: (e) => {
          this.revising.set(false);
          this.reviseError.set(apiErrorMessage(e, 'The slides could not be revised. Please try again.'));
        },
      });
    // Revise what is saved: wait for pending edits to reach the server first.
    const wait = () => (this.saving ? setTimeout(wait, 150) : run());
    wait();
  }

  /** Put back the deck as it was before the last AI revision, citations included. */
  protected undoRevision(): void {
    const snap = this.undoSnapshot();
    if (!snap || this.undoing()) return;
    this.undoing.set(true);
    const slides = snap.slides.map((s) => ({ id: s.id, title: s.title, bullets: s.bullets, notes: s.notes, sources: s.sources }));
    this.api
      .replaceSlides(snap.id, slides)
      .pipe(concatMap(() => this.api.update(snap.id, { title: snap.title, subtitle: snap.subtitle })))
      .subscribe({
        next: (restored) => {
          this.deck.set(restored);
          this.bulletDrafts.clear();
          this.index.set(Math.min(this.index(), restored.slides.length));
          this.undoSnapshot.set(null);
          this.undoing.set(false);
          this.toast.ok('Revision undone.');
        },
        error: (e) => {
          this.undoing.set(false);
          this.toast.error(apiErrorMessage(e, 'The revision could not be undone.'));
        },
      });
  }

  // ---- Present & download ---------------------------------------------------

  /**
   * Present mode always covers the window; true full screen is added on top when the
   * browser allows it (some embedded browsers ignore or never answer the request).
   */
  protected present(): void {
    const el = this.stageEl()?.nativeElement;
    if (!el) return;
    this.presenting.set(true);
    el.focus();
    if (document.fullscreenEnabled && !document.fullscreenElement) {
      el.requestFullscreen?.().catch(() => {});
    }
  }

  protected exitPresent(): void {
    this.presenting.set(false);
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
  }

  /** Leaving full screen (Esc, browser UI) also leaves present mode. */
  protected onFullscreenChange(): void {
    const el = this.stageEl()?.nativeElement;
    if (document.fullscreenElement === el) this.wasFullscreen = true;
    else if (this.wasFullscreen) {
      this.wasFullscreen = false;
      this.presenting.set(false);
    }
  }

  private wasFullscreen = false;

  /** In present mode a click anywhere except a link advances the deck. */
  protected onStageClick(event: MouseEvent): void {
    if (this.presenting() && !(event.target as HTMLElement).closest('a, button')) this.go(this.index() + 1);
  }

  protected download(): void {
    const d = this.deck();
    if (!d || this.downloading()) return;
    // Export what is on screen: save pending edits first.
    this.flushSave();
    this.downloading.set(true);
    const start = () =>
      downloadDeck(this.api, d.id, this.deck()?.title ?? d.title).subscribe({
        next: () => this.downloading.set(false),
        error: (e) => {
          this.downloading.set(false);
          this.toast.error(apiErrorMessage(e, 'The PowerPoint file could not be made.'));
        },
      });
    // Wait for an in-flight save so the file includes the latest changes.
    const wait = () => (this.saving ? setTimeout(wait, 150) : start());
    wait();
  }

  protected onKey(event: KeyboardEvent): void {
    if (!this.deck() || this.reviseOpen()) return;
    const target = event.target as HTMLElement;
    if (target.closest('input, textarea, select, [contenteditable]')) return;
    const onControl = !!target.closest('button, a');
    switch (event.key) {
      case 'Escape':
        if (!this.presenting()) return;
        this.exitPresent();
        break;
      case 'ArrowRight':
      case 'PageDown':
        this.go(this.index() + 1);
        break;
      case ' ':
        if (onControl && !this.presenting()) return;
        event.preventDefault();
        this.go(this.index() + 1);
        break;
      case 'ArrowLeft':
      case 'PageUp':
        this.go(this.index() - 1);
        break;
      case 'Home':
        this.go(0);
        break;
      case 'End':
        this.go(this.total() - 1);
        break;
      default:
        return;
    }
  }
}

/**
 * Steps the slide's --fit scale down until its content fits, starting from full size each
 * time. Every text size on the slide is multiplied by --fit (see slides-viewer-page.scss).
 */
export function fitSlide(slide: HTMLElement): number {
  let fit = 1;
  slide.style.setProperty('--fit', '1');
  // The bullet list can shrink (flex) and spill under the source line without the slide
  // itself overflowing, so check both.
  const list = slide.querySelector<HTMLElement>('.slide__bullets');
  const overflows = () =>
    slide.scrollHeight > slide.clientHeight + 1 || (!!list && list.scrollHeight > list.clientHeight + 1);
  while (overflows() && fit > MIN_FIT) {
    fit = Math.max(MIN_FIT, +(fit - 0.05).toFixed(2));
    slide.style.setProperty('--fit', String(fit));
  }
  return fit;
}
