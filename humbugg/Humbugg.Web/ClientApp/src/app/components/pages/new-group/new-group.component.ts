import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { NgbDateStruct } from '@ng-bootstrap/ng-bootstrap';
import { GroupService } from '../../../services/group.service';
import { ProfileService } from '../../../services/profile.service';
import { Profile } from '../../../models/profile';
import { Group } from '../../../models/group';
import { GroupMember } from '../../../models/groupMember';
import { ErrorHandlerService } from 'src/app/services/error-handler.service';
import { FormControl, Validators } from '@angular/forms';

@Component({
  selector: 'app-new-group',
  templateUrl: './new-group.component.html',
  styleUrls: ['./new-group.component.scss']
})
export class NewGroupComponent implements OnInit {
  profile: Profile = new Profile();
  group: Group = new Group();
  eventDateControl: FormControl = new FormControl('eventDate', Validators.required);
  eventDateStruct: NgbDateStruct;
  signupDeadlineControl: FormControl = new FormControl('signupDeadline', Validators.required);
  signupDeadlineStruct: NgbDateStruct;
  groupMember: GroupMember = new GroupMember();
  askSecretQuestion: boolean = false;
  newGroupId: string;

  constructor(
    private groupService: GroupService,
    private profileService: ProfileService,
    private errorHandlerService: ErrorHandlerService,
    public router: Router) { }

  ngOnInit() {
    this.profileService.get().subscribe(profile => {
      this.profile = profile;
      this.groupMember.firstName = this.profile.firstName;
      this.groupMember.lastName = this.profile.lastName;
      this.groupMember.pictureUrl = this.profile.pictureUrl;
      this.groupMember.userId = this.profile.id;
    });
  }

  createGroup() {
    this.group.groupMembers = [this.groupMember];
    this.group.eventDate = new Date(this.eventDateStruct.year, this.eventDateStruct.month, this.eventDateStruct.day).toISOString();
    this.group.signUpDeadline = new Date(this.signupDeadlineStruct.year, this.signupDeadlineStruct.month, this.signupDeadlineStruct.day).toISOString();
    this.groupService.create(this.group).subscribe(
      response => {
        this.newGroupId = response.id;
        this.router.navigate([`/group-details/${this.newGroupId}`]);
      },
      error => {
        this.errorHandlerService.handleError(error);
      });
  }
}
