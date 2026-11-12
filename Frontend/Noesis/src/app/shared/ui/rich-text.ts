import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { parseBlocks } from '../rich-text';

@Component({
  selector: 'app-rich-text',
  imports: [NgTemplateOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-template #inl let-items>
      @for (x of items; track $index) {
        @switch (x.t) {
          @case ('b') { <strong>{{ x.v }}</strong> }
          @case ('i') { <em>{{ x.v }}</em> }
          @case ('code') { <code>{{ x.v }}</code> }
          @case ('cite') {
            @if (x.n <= citeCount()) {
              <button type="button" class="cite-mark" (click)="cite.emit(x.n)"
                      [attr.aria-label]="'Open source ' + x.n">[{{ x.n }}]</button>
            }
          }
          @default { {{ x.v }} }
        }
      }
    </ng-template>

    @for (b of blocks(); track $index) {
      @switch (b.t) {
        @case ('p') { <p><ng-container *ngTemplateOutlet="inl; context: { $implicit: b.inl }" /></p> }
        @case ('h') { <p class="h"><ng-container *ngTemplateOutlet="inl; context: { $implicit: b.inl }" /></p> }
        @case ('ul') {
          <ul>@for (it of b.items; track $index) { <li><ng-container *ngTemplateOutlet="inl; context: { $implicit: it }" /></li> }</ul>
        }
        @case ('ol') {
          <ol>@for (it of b.items; track $index) { <li><ng-container *ngTemplateOutlet="inl; context: { $implicit: it }" /></li> }</ol>
        }
        @case ('pre') { <pre>{{ b.v }}</pre> }
      }
    }
  `,
  styles: `
    :host { display: block; }
    p, ul, ol, pre { margin: 0 0 0.75em; }
    :host > :last-child { margin-bottom: 0; }
    ul, ol { padding-left: 1.3em; }
    li { margin-bottom: 0.25em; }
    .h { font-weight: 600; }
    code { font-family: var(--font-mono); font-size: 0.85em; padding: 1px 4px; border-radius: 3px; background: var(--paper-sunk); }
    pre {
      font-family: var(--font-mono); font-size: var(--text-xs); line-height: 1.6;
      padding: var(--space-3); overflow-x: auto; border-radius: var(--radius-sm);
      background: var(--paper-sunk); border: 1px solid var(--rule);
    }
  `,
})
export class RichText {
  readonly text = input.required<string>();
  readonly citeCount = input(0);
  readonly cite = output<number>();
  protected readonly blocks = computed(() => parseBlocks(this.text()));
}
