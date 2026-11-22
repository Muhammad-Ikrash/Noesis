import { Observable, map } from 'rxjs';
import { SlidesService } from '../../core/services/slides.service';
import { downloadBlob } from '../../shared/download';

const PPTX_TYPE = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';

/** File-system friendly "<title>.pptx", keeping spaces and letters in any language. */
export function pptxFilename(title: string): string {
  const stem = title.replace(/[\\/:*?"<>|\u0000-\u001f]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80);
  return `${stem || 'slides'}.pptx`;
}

/** Fetch the deck as PowerPoint and save it. Errors are left to the caller. */
export function downloadDeck(api: SlidesService, id: string, title: string): Observable<void> {
  return api.pptx(id).pipe(map((data) => downloadBlob(new Blob([data], { type: PPTX_TYPE }), pptxFilename(title))));
}
