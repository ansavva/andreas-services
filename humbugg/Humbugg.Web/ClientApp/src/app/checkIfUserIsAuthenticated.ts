import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { AuthService } from './services/auth.service';

export function checkIfUserIsAuthenticated(authService: AuthService) {
  return () => {
    return authService.updateUserAuthenticationStatus().pipe(catchError(_ => {
      return of(null);
    })).toPromise();
  };
}
