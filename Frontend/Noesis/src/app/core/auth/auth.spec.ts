import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot, provideRouter } from '@angular/router';
import { authGuard } from './auth.guard';
import { AUTH_ENABLED, AuthService } from './auth.service';

describe('AuthService', () => {
  beforeEach(() => TestBed.configureTestingModule({}));

  it('is local-only for now', () => {
    expect(AUTH_ENABLED).toBe(false);
  });

  it('counts as signed in without a token while auth is disabled', () => {
    const auth = TestBed.inject(AuthService);
    expect(auth.accessToken()).toBeNull();
    expect(auth.isAuthenticated()).toBe(true);
  });

  it('stores and clears the token', () => {
    const auth = TestBed.inject(AuthService);
    auth.setToken('t');
    expect(auth.accessToken()).toBe('t');
    auth.setToken(null);
    expect(auth.accessToken()).toBeNull();
  });
});

describe('authGuard', () => {
  it('lets every route through while auth is disabled', () => {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
    );
    expect(result).toBe(true);
  });
});
