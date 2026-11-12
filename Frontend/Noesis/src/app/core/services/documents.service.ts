import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api/api.config';
import { DocumentDetail, DocumentOut, UploadOut } from '../api/models';

@Injectable({ providedIn: 'root' })
export class DocumentsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(API_BASE_URL)}/documents`;

  list(): Observable<DocumentOut[]> {
    return this.http.get<DocumentOut[]>(this.base);
  }

  get(id: string): Observable<DocumentDetail> {
    return this.http.get<DocumentDetail>(`${this.base}/${id}`);
  }

  upload(file: File): Observable<UploadOut> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http.post<UploadOut>(this.base, body);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  fileUrl(id: string): string {
    return `${this.base}/${id}/file`;
  }

  file(id: string): Observable<ArrayBuffer> {
    return this.http.get(this.fileUrl(id), { responseType: 'arraybuffer' });
  }
}
