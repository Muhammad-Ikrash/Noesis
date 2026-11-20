import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api/api.config';
import { Deck, DeckCreate, DeckSummary, Flashcard } from '../api/models';

@Injectable({ providedIn: 'root' })
export class FlashcardService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(API_BASE_URL)}/flashcards`;

  list(): Observable<DeckSummary[]> {
    return this.http.get<DeckSummary[]>(this.base);
  }

  get(id: string): Observable<Deck> {
    return this.http.get<Deck>(`${this.base}/${id}`);
  }

  create(body: DeckCreate): Observable<Deck> {
    return this.http.post<Deck>(this.base, body);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  /** known = "Got it", false = "Still learning". */
  mark(id: string, cardId: string, known: boolean): Observable<Flashcard> {
    return this.http.patch<Flashcard>(`${this.base}/${id}/cards/${cardId}`, { known });
  }

  reset(id: string): Observable<Deck> {
    return this.http.post<Deck>(`${this.base}/${id}/reset`, {});
  }
}
