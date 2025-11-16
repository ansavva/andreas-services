import { Component, OnInit, OnDestroy } from '@angular/core';
import { BreakpointObserver, Breakpoints } from '@angular/cdk/layout';
import { Router } from '@angular/router';
import { Subscription, Observable } from 'rxjs';
import { map, share } from 'rxjs/operators';

import {Profile} from '../../../models/profile';
import {AuthService} from '../../../services/auth.service';
import {ProfileService} from '../../../services/profile.service';

//https://www.youtube.com/watch?v=Q6qhzG7mObU
@Component({
  selector: 'app-main-nav',
  templateUrl: './main-nav.component.html',
  styleUrls: ['./main-nav.component.scss']
})
export class MainNavComponent implements OnInit, OnDestroy {
  isUserAuthenticated = false;
  isUserAuthenticatedSubscription: Subscription;
  profile: Profile = new Profile();
  navbarOpen = false;

  isHandset$: Observable<boolean> = this.breakpointObserver.observe(Breakpoints.Handset)
    .pipe(
      map(result => result.matches),
      share()
    );

  constructor(
    private breakpointObserver: BreakpointObserver, 
    private authService: AuthService, 
    private profileService: ProfileService,
    public router: Router) {}

  ngOnInit() {
    this.isUserAuthenticatedSubscription = this.authService.isUserAuthenticated.subscribe(isAuthenticated => {
      this.isUserAuthenticated = isAuthenticated;
      if (this.isUserAuthenticated) {
        this.profileService.get().subscribe(profile => {
            this.profile = profile;
          }
        );
      }
    });
  }

  ngOnDestroy() {
    this.isUserAuthenticatedSubscription.unsubscribe();
  }

  logout() {
    this.authService.logout();
  }

  login() {
    this.authService.login(null);
  }

  toggleNavbar() {
    this.navbarOpen = !this.navbarOpen;
  }
}
