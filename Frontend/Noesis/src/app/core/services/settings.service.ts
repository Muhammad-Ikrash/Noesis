import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api/api.config';
import { UserSettings } from '../api/models';

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(API_BASE_URL)}/settings`;

  get(): Observable<UserSettings> {
    return this.http.get<UserSettings>(this.base);
  }

  update(body: UserSettings): Observable<UserSettings> {
    return this.http.put<UserSettings>(this.base, body);
  }
}
