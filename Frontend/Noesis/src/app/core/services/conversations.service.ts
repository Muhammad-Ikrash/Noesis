import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api/api.config';
import {
  AskRequest, AskResponse, Conversation, ConversationCreate, ConversationDetail, ConversationUpdate,
} from '../api/models';

@Injectable({ providedIn: 'root' })
export class ConversationsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(API_BASE_URL)}/conversations`;

  list(): Observable<Conversation[]> {
    return this.http.get<Conversation[]>(this.base);
  }

  get(id: string): Observable<ConversationDetail> {
    return this.http.get<ConversationDetail>(`${this.base}/${id}`);
  }

  create(body: ConversationCreate): Observable<Conversation> {
    return this.http.post<Conversation>(this.base, body);
  }

  update(id: string, body: ConversationUpdate): Observable<Conversation> {
    return this.http.patch<Conversation>(`${this.base}/${id}`, body);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  ask(id: string, body: AskRequest): Observable<AskResponse> {
    return this.http.post<AskResponse>(`${this.base}/${id}/messages`, body);
  }
}
