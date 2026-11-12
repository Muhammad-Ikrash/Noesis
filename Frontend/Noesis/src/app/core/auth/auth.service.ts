import { Injectable, computed, signal } from '@angular/core';

/**
 * Authentication seam. The backend currently runs local-only with a single implicit user,
 * so the app is always "signed in". When auth lands:
 *  - set AUTH_ENABLED to true,
 *  - implement login()/logout() against /api/v1/auth,
 *  - the interceptor and guard below start working without other changes.
 */
export const AUTH_ENABLED = false;

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly token = signal<string | null>(null);

  readonly accessToken = this.token.asReadonly();
  readonly isAuthenticated = computed(() => !AUTH_ENABLED || this.token() !== null);

  setToken(token: string | null): void {
    this.token.set(token);
  }
}
