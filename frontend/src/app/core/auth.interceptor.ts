import { HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, tap, throwError } from 'rxjs';
import { AuthService } from './auth.service';
import { NetworkActivityService } from './network-activity.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const activity = inject(NetworkActivityService);
  const apiRequest =
    typeof window !== 'undefined' &&
    (window.location.protocol === 'capacitor:' ||
      (window.location.hostname === 'localhost' && window.location.port === '')) &&
    request.url.startsWith('/api/v1/')
      ? request.clone({ url: `https://erp.goesautoparts.com.br${request.url}` })
      : request;
  const secured = auth.token
    ? apiRequest.clone({ setHeaders: { Authorization: `Bearer ${auth.token}` } })
    : apiRequest;
  activity.started();
  return next(secured).pipe(
    tap((event) => {
      if (event instanceof HttpResponse) activity.settled(event.status);
    }),
    catchError((error: HttpErrorResponse) => {
      activity.settled(error.status ?? 0);
      if (
        error.status === 401 &&
        !request.url.endsWith('/auth/login') &&
        !request.url.endsWith('/auth/logout')
      )
        auth.logout(false);
      return throwError(() => error);
    }),
  );
};
