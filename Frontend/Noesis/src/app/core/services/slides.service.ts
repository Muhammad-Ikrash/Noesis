import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api/api.config';
import { SlideDeck, SlideDeckCreate, SlideDeckSummary, SlideDeckUpdate, SlideEdit } from '../api/models';

@Injectable({ providedIn: 'root' })
export class SlidesService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(API_BASE_URL)}/slides`;

  list(): Observable<SlideDeckSummary[]> {
    return this.http.get<SlideDeckSummary[]>(this.base);
  }

  get(id: string): Observable<SlideDeck> {
    return this.http.get<SlideDeck>(`${this.base}/${id}`);
  }

  create(body: SlideDeckCreate): Observable<SlideDeck> {
    return this.http.post<SlideDeck>(this.base, body);
  }

  /** Title, subtitle and/or design; fields left out are unchanged. */
  update(id: string, body: SlideDeckUpdate): Observable<SlideDeck> {
    return this.http.patch<SlideDeck>(`${this.base}/${id}`, body);
  }

  /** Save the full edited slide list in its new order. */
  replaceSlides(id: string, slides: SlideEdit[]): Observable<SlideDeck> {
    return this.http.put<SlideDeck>(`${this.base}/${id}/slides`, { slides });
  }

  /** Ask the AI to change one slide (slideId) or the whole deck. */
  revise(id: string, instruction: string, slideId?: string): Observable<SlideDeck> {
    return this.http.post<SlideDeck>(`${this.base}/${id}/revise`, { instruction, slide_id: slideId ?? null });
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  /** Editable PowerPoint version of the deck. */
  pptx(id: string): Observable<ArrayBuffer> {
    return this.http.get(`${this.base}/${id}/pptx`, { responseType: 'arraybuffer' });
  }
}
