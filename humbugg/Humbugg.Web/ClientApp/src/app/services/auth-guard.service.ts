import { Injectable } from '@angular/core';
import { Router, CanActivate, RouterStateSnapshot, ActivatedRouteSnapshot } from '@angular/router';
import { AuthService } from './auth.service';
import { Observable } from "rxjs";

@Injectable()
export class AuthGuardService implements CanActivate {

  constructor(public authService: AuthService, public router: Router) {}

  canActivate(route: ActivatedRouteSnapshot, state: RouterStateSnapshot): Observable<boolean> {
    this.authService.isUserAuthenticated.subscribe(isAuthenticated => {
      if (!isAuthenticated) {
          this.authService.login(state.url);
      }
    });
    return this.authService.isUserAuthenticated;
  }
}
