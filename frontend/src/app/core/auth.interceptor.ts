import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const apiRequest = typeof window !== 'undefined' && (window.location.protocol === 'capacitor:' || (window.location.hostname === 'localhost' && window.location.port === '')) && request.url.startsWith('/api/v1/')
    ? request.clone({ url: `https://erp.goesautoparts.com.br${request.url}` })
    : request;
  const secured = auth.token
    ? apiRequest.clone({ setHeaders: { Authorization: `Bearer ${auth.token}` } })
    : apiRequest;
  return next(secured).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !request.url.endsWith('/auth/login') && !request.url.endsWith('/auth/logout')) auth.logout(false);
      return throwError(() => error);
    }),
  );
};
