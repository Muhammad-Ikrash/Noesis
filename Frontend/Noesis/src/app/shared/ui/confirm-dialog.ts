import {
  ChangeDetectionStrategy, Component, ElementRef, effect, input, output, viewChild,
} from '@angular/core';

/** Native <dialog> confirmation. Open by setting [open]=true; emits confirmed/cancelled. */
@Component({
  selector: 'app-confirm-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dialog #dlg class="dialog" (close)="cancelled.emit()" (cancel)="cancelled.emit()">
      <header><h3>{{ title() }}</h3></header>
      <div class="dialog__body"><p class="muted">{{ message() }}</p></div>
      <footer>
        <button class="btn" type="button" (click)="dlg.close()" [disabled]="busy()">Cancel</button>
        <button class="btn" [class.btn--danger-solid]="danger()" [class.btn--primary]="!danger()"
                type="button" (click)="confirmed.emit()" [disabled]="busy()">
          @if (busy()) { <span class="spinner"></span> }
          {{ confirmLabel() }}
        </button>
      </footer>
    </dialog>
  `,
})
export class ConfirmDialog {
  readonly open = input(false);
  readonly title = input('Are you sure?');
  readonly message = input('');
  readonly confirmLabel = input('Confirm');
  readonly danger = input(false);
  readonly busy = input(false);
  readonly confirmed = output<void>();
  readonly cancelled = output<void>();

  private readonly dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');

  constructor() {
    effect(() => {
      const el = this.dlg().nativeElement;
      if (this.open() && !el.open) el.showModal();
      if (!this.open() && el.open) el.close();
    });
  }
}
