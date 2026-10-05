import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';
import { canAccessPage } from './user-access';

export const accessGuard: CanActivateFn = (_route, state) => {
  const router = inject(Router);
  return canAccessPage(inject(AuthService).user()?.role, state.url)
    ? true
    : router.createUrlTree(['/dashboard']);
};
