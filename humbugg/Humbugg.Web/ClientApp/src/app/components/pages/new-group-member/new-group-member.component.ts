import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import * as moment from 'moment';
import { ProfileService } from '../../../services/profile.service';
import { NotificationService } from '../../../services/notification.service';
import { GroupService } from '../../../services/group.service';
import { GroupMemberService } from '../../../services/group-member.service';
import { Group } from '../../../models/group';
import { GroupMember } from '../../../models/groupMember';
import { Profile } from '../../../models/profile';
import { ErrorHandlerService } from 'src/app/services/error-handler.service';

@Component({
  selector: 'app-new-group-member',
  templateUrl: './new-group-member.component.html',
  styleUrls: ['./new-group-member.component.scss']
})
export class NewGroupMemberComponent implements OnInit {
  groupId: string;
  profile: Profile = new Profile();
  group: Group = new Group();
  groupMember: GroupMember = new GroupMember();

  constructor(
    private profileService: ProfileService,
    private notifyService: NotificationService,
    private groupService: GroupService,
    private groupMemberService: GroupMemberService,
    private errorHandlerService: ErrorHandlerService,
    public router: Router,
    public route: ActivatedRoute
  ) { }

  ngOnInit() {
    this.route.params.subscribe(params => {
      this.groupId = params['id'];
      this.profileService.get().subscribe(profile => {
        this.profile = profile;
        this.groupMember.firstName = this.profile.firstName;
        this.groupMember.lastName = this.profile.lastName;
        this.groupMember.pictureUrl = this.profile.pictureUrl;
        this.groupMember.userId = this.profile.id;
        this.groupMember.groupId = this.groupId;
        this.groupService.get(this.groupId).subscribe(
          group => {
            this.group = group;
            this.group.eventDateDisplay = moment(group.eventDate).format('dddd, MMMM Do YYYY');
            this.group.signUpDeadlineDisplay = moment(group.signUpDeadline).format('dddd, MMMM Do YYYY');
          },
          error => {
            this.errorHandlerService.handleError(error);
          });
      });
    });
  }

  createGroupMember() {
    this.groupMemberService.create(this.groupMember).subscribe(
      response => {
        this.router.navigate([`/group-details/${this.groupId}`]);
      },
      error => {
        this.errorHandlerService.handleError(error);
      });
  }

  hasSecretQuestion() {
    return this.group.secretQuestionAnswer != null;
  }
}
