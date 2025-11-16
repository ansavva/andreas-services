import { Component, OnInit } from '@angular/core';

import { Profile } from '../../../models/profile';
import { NotificationService } from '../../../services/notification.service'
import { ProfileService } from '../../../services/profile.service';
import { ErrorHandlerService } from 'src/app/services/error-handler.service';

@Component({
  selector: 'app-profile',
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.scss']
})
export class ProfileComponent implements OnInit {
  profile: Profile = new Profile();

  constructor(
    private profileService: ProfileService,
    private notifyService: NotificationService,
    private errorHandlerService: ErrorHandlerService) { }

  ngOnInit() {
    this.profileService.get().subscribe(profile => {
      this.profile = profile;
    });
  }

  onSubmit() {
    this.profileService.update(this.profile).subscribe(
      response => {
        this.notifyService.success('Profile Updated!');
      },
      error => {
        this.errorHandlerService.handleError(error);
      });
  }
}
