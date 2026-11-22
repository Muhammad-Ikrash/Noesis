import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { authInterceptor } from '../auth/auth.interceptor';
import { AuthService } from '../auth/auth.service';
import { ToastService } from '../services/toast.service';
import { errorInterceptor } from './error.interceptor';

describe('HTTP interceptors', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let toast: ToastService;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    toast = TestBed.inject(ToastService);
  });

  afterEach(() => {
    backend.verify();
    vi.useRealTimers();
  });

  describe('authInterceptor', () => {
    it('sends no Authorization header while there is no token', () => {
      http.get('/api/v1/documents').subscribe();
      const req = backend.expectOne('/api/v1/documents');
      expect(req.request.headers.has('Authorization')).toBe(false);
      req.flush([]);
    });

    it('adds a bearer token once one is set', () => {
      TestBed.inject(AuthService).setToken('abc123');
      http.get('/api/v1/documents').subscribe();
      const req = backend.expectOne('/api/v1/documents');
      expect(req.request.headers.get('Authorization')).toBe('Bearer abc123');
      req.flush([]);
    });
  });

  describe('errorInterceptor', () => {
    it('shows one offline toast for network failures and still rethrows', () => {
      const errors: unknown[] = [];
      http.get('/a').subscribe({ error: (e) => errors.push(e) });
      http.get('/b').subscribe({ error: (e) => errors.push(e) });
      backend.expectOne('/a').error(new ProgressEvent('error'), { status: 0 });
      backend.expectOne('/b').error(new ProgressEvent('error'), { status: 0 });

      expect(errors).toHaveLength(2);
      expect(toast.toasts()).toHaveLength(1);
      expect(toast.toasts()[0]).toMatchObject({ kind: 'error', key: 'offline' });
    });

    it('leaves other HTTP errors to the page', () => {
      let status = 0;
      http.get('/missing').subscribe({ error: (e) => (status = e.status) });
      backend.expectOne('/missing').flush({ detail: 'Not found' }, { status: 404, statusText: 'Not Found' });

      expect(status).toBe(404);
      expect(toast.toasts()).toHaveLength(0);
    });
  });
});
