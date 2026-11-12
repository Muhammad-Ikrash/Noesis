import { InjectionToken } from '@angular/core';

/** Backend base URL. The dev server proxies /api to the FastAPI app (proxy.conf.json). */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL', {
  factory: () => '/api/v1',
});
