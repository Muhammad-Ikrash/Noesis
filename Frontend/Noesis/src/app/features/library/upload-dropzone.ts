import { ChangeDetectionStrategy, Component, inject, output, signal } from '@angular/core';
import { DocumentOut } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { DocumentsService } from '../../core/services/documents.service';
import { formatBytes } from '../../shared/format';
import { Icon } from '../../shared/ui/icon';

interface UploadItem {
  key: number;
  name: string;
  size: number;
  state: 'uploading' | 'done' | 'duplicate' | 'error';
  message?: string;
}

@Component({
  selector: 'app-upload-dropzone',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="drop" [class.is-over]="over()"
           (dragover)="$event.preventDefault(); over.set(true)" (dragleave)="over.set(false)"
           (drop)="onDrop($event)">
      <input type="file" accept="application/pdf,.pdf" multiple class="sr-only" (change)="onPick($event)" />
      <app-icon name="upload" [size]="22" />
      <span class="drop__title">Drop PDFs here or <u>browse</u></span>
      <span class="drop__hint">Notes, textbooks, slides. Text is read page by page; scanned pages are flagged.</span>
    </label>

    @if (items().length) {
      <ul class="queue" aria-label="Uploads">
        @for (item of items(); track item.key) {
          <li [class]="'queue__item is-' + item.state">
            <app-icon name="file" [size]="16" />
            <span class="queue__name">{{ item.name }}</span>
            <span class="mono muted">{{ size(item.size) }}</span>
            @switch (item.state) {
              @case ('uploading') { <span class="spinner" aria-label="Uploading"></span> }
              @case ('done') { <span class="pill pill--ok">uploaded</span> }
              @case ('duplicate') { <span class="pill">already in library</span> }
              @case ('error') { <span class="pill pill--danger" [title]="item.message">failed</span> }
            }
          </li>
          @if (item.state === 'error') { <li class="queue__error">{{ item.message }}</li> }
        }
      </ul>
      @if (!busy()) {
        <button class="btn btn--quiet btn--sm clear" type="button" (click)="items.set([])">Clear list</button>
      }
    }
  `,
  styles: `
    :host { display: block; }
    .drop {
      display: grid; justify-items: center; gap: 6px;
      padding: var(--space-6) var(--space-4);
      border: 1.5px dashed var(--rule-strong); border-radius: var(--radius);
      background: repeating-linear-gradient(0deg, transparent 0 27px, color-mix(in srgb, var(--rule), transparent 50%) 27px 28px);
      color: var(--ink-2); text-align: center; cursor: pointer;
      transition: border-color .15s, background-color .15s;
      &:hover, &.is-over { border-color: var(--pen); background-color: var(--pen-soft); color: var(--ink); }
      &:focus-within { outline: 2px solid var(--focus); outline-offset: 2px; }
    }
    .drop__title { font-family: var(--font-read); font-size: var(--text-lg); color: var(--ink); }
    .drop__hint { font-size: var(--text-sm); max-width: 46ch; }
    .queue { list-style: none; margin: var(--space-3) 0 0; padding: 0; display: grid; gap: 2px; }
    .queue__item {
      display: flex; align-items: center; gap: var(--space-3);
      padding: 6px var(--space-2); font-size: var(--text-sm); border-bottom: 1px solid var(--rule);
    }
    .queue__name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .queue__error { padding: 2px var(--space-2) 8px 36px; font-size: var(--text-xs); color: var(--danger); }
    .clear { margin-top: var(--space-2); }
  `,
})
export class UploadDropzone {
  private readonly docs = inject(DocumentsService);
  readonly uploaded = output<DocumentOut>();

  protected readonly over = signal(false);
  protected readonly items = signal<UploadItem[]>([]);
  protected readonly busy = signal(false);
  protected readonly size = formatBytes;
  private key = 0;
  private inFlight = 0;

  protected onPick(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.start(Array.from(input.files ?? []));
    input.value = '';
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.over.set(false);
    this.start(Array.from(event.dataTransfer?.files ?? []));
  }

  private start(files: File[]): void {
    for (const file of files) {
      const key = ++this.key;
      const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
      this.items.update((l) => [{ key, name: file.name, size: file.size, state: 'uploading' }, ...l]);
      if (!isPdf) {
        this.patch(key, { state: 'error', message: 'Only PDF files can be added.' });
        continue;
      }
      this.inFlight++;
      this.busy.set(true);
      this.docs.upload(file).subscribe({
        next: (res) => {
          this.patch(key, { state: res.created ? 'done' : 'duplicate' });
          this.uploaded.emit(res.document);
          this.settle();
        },
        error: (err) => {
          this.patch(key, { state: 'error', message: apiErrorMessage(err, 'Upload failed.') });
          this.settle();
        },
      });
    }
  }

  private settle(): void {
    this.inFlight--;
    this.busy.set(this.inFlight > 0);
  }

  private patch(key: number, change: Partial<UploadItem>): void {
    this.items.update((l) => l.map((i) => (i.key === key ? { ...i, ...change } : i)));
  }
}
