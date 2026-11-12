import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { ToastService } from '../services/toast.service';
import { apiErrorMessage } from './api-error';

/** Surfaces connectivity failures globally; feature code handles everything else in context. */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(ToastService);
  return next(req).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 0) {
        toast.error(apiErrorMessage(err), 'offline');
      }
      return throwError(() => err);
    }),
  );
};
