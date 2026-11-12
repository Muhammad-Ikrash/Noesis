import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api/api.config';
import { AttemptResult, Quiz, QuizCreate, QuizSummary } from '../api/models';

@Injectable({ providedIn: 'root' })
export class QuizService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(API_BASE_URL)}/quizzes`;

  list(): Observable<QuizSummary[]> {
    return this.http.get<QuizSummary[]>(this.base);
  }

  get(id: string): Observable<Quiz> {
    return this.http.get<Quiz>(`${this.base}/${id}`);
  }

  create(body: QuizCreate): Observable<Quiz> {
    return this.http.post<Quiz>(this.base, body);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  submit(id: string, answers: (number | null)[]): Observable<AttemptResult> {
    return this.http.post<AttemptResult>(`${this.base}/${id}/attempts`, { answers });
  }

  attempt(id: string, attemptId: string): Observable<AttemptResult> {
    return this.http.get<AttemptResult>(`${this.base}/${id}/attempts/${attemptId}`);
  }
}
