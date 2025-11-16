import { Component, OnInit } from '@angular/core';
import { Router, CanActivate } from '@angular/router';
import { Subscription } from 'rxjs';

import { AuthService } from '../../../services/auth.service';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss']
})
export class HomeComponent implements OnInit {
  isUserAuthenticated = false;
  isUserAuthenticatedSubscription: Subscription;

  constructor(private authService: AuthService, public router: Router) { }

  ngOnInit() {
    this.isUserAuthenticatedSubscription = this.authService.isUserAuthenticated.subscribe(isAuthenticated => {
      this.isUserAuthenticated = isAuthenticated;
    });
  }

  ngOnDestroy() {
    this.isUserAuthenticatedSubscription.unsubscribe();
  }

  getStarted() {
    this.router.navigate(['new-group']);
  }
}
