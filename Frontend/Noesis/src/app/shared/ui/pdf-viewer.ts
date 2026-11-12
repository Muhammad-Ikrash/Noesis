import {
  ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, effect, inject, input,
  signal, untracked, viewChild,
} from '@angular/core';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { firstValueFrom } from 'rxjs';
import { apiErrorMessage } from '../../core/http/api-error';
import { DocumentsService } from '../../core/services/documents.service';
import { Icon } from './icon';

export interface ViewerTarget {
  page: number;
  quote?: string | null;
  /** Changes on every request so clicking the same citation twice scrolls again. */
  nonce: number;
}

interface Shell {
  n: number;
  w: number;
  h: number;
}

type PdfJs = typeof import('pdfjs-dist');
let pdfjsPromise: Promise<PdfJs> | null = null;

function loadPdfJs(): Promise<PdfJs> {
  pdfjsPromise ??= import('pdfjs-dist').then((m) => {
    m.GlobalWorkerOptions.workerSrc = '/pdfjs/pdf.worker.min.mjs';
    return m;
  });
  return pdfjsPromise;
}

const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
const MIN_SCALE = 0.5;
const MAX_SCALE = 3;

@Component({
  selector: 'app-pdf-viewer',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pdf-viewer.html',
  styleUrl: './pdf-viewer.scss',
})
export class PdfViewer {
  readonly documentId = input.required<string>();
  readonly target = input<ViewerTarget | null>(null);

  private readonly docs = inject(DocumentsService);
  private readonly scroller = viewChild.required<ElementRef<HTMLElement>>('scroller');

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly shells = signal<Shell[]>([]);
  protected readonly current = signal(1);
  protected readonly scale = signal(1);
  protected readonly total = computed(() => this.shells().length);
  protected readonly zoomLabel = computed(() => `${Math.round(this.scale() * 100)}%`);

  private pdf: PDFDocumentProxy | null = null;
  private pdfjs: PdfJs | null = null;
  private baseWidth = 600;
  private generation = 0;
  private rendered = new Map<number, number>(); // page -> generation rendered at
  private pendingHighlight: { page: number; quote: string | null } | null = null;
  private observer: IntersectionObserver | null = null;
  private scrollRaf = 0;

  constructor() {
    effect(() => {
      const id = this.documentId();
      untracked(() => this.open(id));
    });

    effect(() => {
      const t = this.target();
      if (t && this.total()) untracked(() => this.goTo(t.page, t.quote ?? null));
    });

    inject(DestroyRef).onDestroy(() => {
      this.observer?.disconnect();
      void this.pdf?.destroy();
    });
  }

  protected retry(): void {
    this.open(this.documentId());
  }

  private async open(id: string): Promise<void> {
    const gen = ++this.generation;
    this.loading.set(true);
    this.error.set(null);
    this.shells.set([]);
    this.rendered.clear();
    this.observer?.disconnect();
    void this.pdf?.destroy();
    this.pdf = null;

    try {
      const [pdfjs, data] = await Promise.all([loadPdfJs(), firstValueFrom(this.docs.file(id))]);
      if (gen !== this.generation) return;
      this.pdfjs = pdfjs;
      const pdf = await pdfjs.getDocument({ data: new Uint8Array(data) }).promise;
      if (gen !== this.generation) {
        void pdf.destroy();
        return;
      }
      this.pdf = pdf;
      const first = (await pdf.getPage(1)).getViewport({ scale: 1 });
      this.baseWidth = first.width;
      const ratio = first.height / first.width;
      const available = this.scroller().nativeElement.clientWidth - 48;
      const scale = clamp(available / first.width, MIN_SCALE, 1.6);
      this.scale.set(scale);
      this.shells.set(
        Array.from({ length: pdf.numPages }, (_, i) => ({ n: i + 1, w: first.width * scale, h: first.width * ratio * scale })),
      );
      this.current.set(1);
      this.loading.set(false);
      queueMicrotask(() => {
        this.observe();
        const t = this.target();
        if (t) this.goTo(t.page, t.quote ?? null);
      });
    } catch (e) {
      if (gen !== this.generation) return;
      this.loading.set(false);
      this.error.set(apiErrorMessage(e, 'This PDF could not be displayed.'));
    }
  }

  private observe(): void {
    this.observer?.disconnect();
    const root = this.scroller().nativeElement;
    this.observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) void this.render(Number((e.target as HTMLElement).dataset['page']));
        }
      },
      { root, rootMargin: '600px 0px' },
    );
    root.querySelectorAll<HTMLElement>('.pg').forEach((el) => this.observer!.observe(el));
  }

  private shellEl(n: number): HTMLElement | null {
    return this.scroller().nativeElement.querySelector(`.pg[data-page="${n}"]`);
  }

  private async render(n: number): Promise<void> {
    const gen = this.generation;
    if (!this.pdf || !this.pdfjs || this.rendered.get(n) === gen) return;
    this.rendered.set(n, gen);
    const el = this.shellEl(n);
    if (!el) return;

    const page = await this.pdf.getPage(n);
    const scale = this.scale();
    const vp = page.getViewport({ scale });
    const dpr = window.devicePixelRatio || 1;
    const canvas = document.createElement('canvas');
    canvas.width = Math.floor(vp.width * dpr);
    canvas.height = Math.floor(vp.height * dpr);
    canvas.style.width = `${vp.width}px`;
    canvas.style.height = `${vp.height}px`;
    const text = document.createElement('div');
    text.className = 'textLayer';

    try {
      await page.render({ canvas, viewport: vp, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined }).promise;
      if (gen !== this.generation) return;
      el.replaceChildren(canvas, text);
      el.style.width = `${vp.width}px`;
      el.style.height = `${vp.height}px`;
      el.style.setProperty('--scale-factor', String(scale));
      el.style.setProperty('--user-unit', '1');
      el.style.setProperty('--total-scale-factor', String(scale));
      await new this.pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container: text, viewport: vp }).render();
      if (this.pendingHighlight?.page === n) this.highlight(n, this.pendingHighlight.quote);
    } catch {
      this.rendered.delete(n);
    }
  }

  private goTo(page: number, quote: string | null): void {
    const n = clamp(page, 1, this.total());
    const el = this.shellEl(n);
    if (!el) return;
    el.scrollIntoView({ block: 'start', behavior: 'smooth' });
    this.current.set(n);
    this.pendingHighlight = { page: n, quote };
    if (this.rendered.get(n) === this.generation && el.querySelector('.textLayer span')) this.highlight(n, quote);
  }

  private highlight(n: number, quote: string | null): void {
    const root = this.scroller().nativeElement;
    root.querySelectorAll('.nx-hl').forEach((s) => s.classList.remove('nx-hl'));
    root.querySelectorAll('.pg.is-flash').forEach((s) => s.classList.remove('is-flash'));
    const el = this.shellEl(n);
    if (!el) return;
    this.pendingHighlight = null;

    let hits = 0;
    if (quote) {
      const q = norm(quote);
      el.querySelectorAll<HTMLElement>('.textLayer span').forEach((span) => {
        const t = norm(span.textContent ?? '');
        if (t.length >= 4 && (q.includes(t) || (q.length >= 12 && t.includes(q)))) {
          span.classList.add('nx-hl');
          hits++;
        }
      });
    }
    if (!hits) {
      el.classList.add('is-flash');
      setTimeout(() => el.classList.remove('is-flash'), 1600);
    }
  }

  protected onScroll(): void {
    cancelAnimationFrame(this.scrollRaf);
    this.scrollRaf = requestAnimationFrame(() => {
      const root = this.scroller().nativeElement;
      const mid = root.scrollTop + root.clientHeight / 3;
      let page = 1;
      for (const el of Array.from(root.querySelectorAll<HTMLElement>('.pg'))) {
        if (el.offsetTop <= mid) page = Number(el.dataset['page']);
        else break;
      }
      this.current.set(page);
    });
  }

  protected step(delta: number): void {
    this.goTo(this.current() + delta, null);
  }

  protected jump(event: Event): void {
    const input = event.target as HTMLInputElement;
    const n = Number(input.value);
    if (Number.isFinite(n) && n >= 1) this.goTo(n, null);
    input.value = String(this.current());
  }

  protected zoom(factor: number | 'fit'): void {
    const available = this.scroller().nativeElement.clientWidth - 48;
    const next = factor === 'fit' ? available / this.baseWidth : this.scale() * factor;
    const scale = clamp(next, MIN_SCALE, MAX_SCALE);
    if (Math.abs(scale - this.scale()) < 0.01) return;
    const keep = this.current();
    const ratio = this.scale() / scale;
    this.scale.set(scale);
    this.generation++;
    this.rendered.clear();
    this.shells.update((list) => list.map((s) => ({ ...s, w: s.w / ratio, h: s.h / ratio })));
    queueMicrotask(() => {
      this.scroller().nativeElement.querySelectorAll('.pg').forEach((el) => el.replaceChildren());
      this.observe();
      this.shellEl(keep)?.scrollIntoView({ block: 'start' });
    });
  }
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}
