import { Component, OnInit } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import * as moment from 'moment';
import { NotificationService } from '../../../services/notification.service';
import { GroupService } from '../../../services/group.service';
import { ProfileService } from '../../../services/profile.service';
import { UtilityService } from 'src/app/services/utility.service';
import { Profile } from '../../../models/profile';
import { Group } from '../../../models/group';
import { GroupMember } from '../../../models/groupMember';
import { ConfirmationComponent } from '../../dialogs/confirmation/confirmation.component';
import { ErrorHandlerService } from 'src/app/services/error-handler.service';
import { NgbModal } from '@ng-bootstrap/ng-bootstrap';
import { EditMatchesComponent } from '../../dialogs/edit-matches/edit-matches.component';

@Component({
  selector: 'app-group-details',
  templateUrl: './group-details.component.html',
  styleUrls: ['./group-details.component.scss']
})
export class GroupDetailsComponent implements OnInit {
  profile: Profile = new Profile();
  group: Group = new Group();
  myGroupMember: GroupMember = new GroupMember();
  shareLink: string;
  showMatches: boolean;
  hasSecretQuestion: boolean;

  constructor(
    private groupService: GroupService,
    private notifyService: NotificationService,
    private profileService: ProfileService,
    private utilityService: UtilityService,
    private errorHandlerService: ErrorHandlerService,
    public route: ActivatedRoute,
    public router: Router,
    public dialog: NgbModal) {
    this.profile.pictureUrl = '';
    this.myGroupMember.pictureUrl = '';
  }

  ngOnInit() {
    this.route.params.subscribe(params => {
      const groupId = params.id;
      this.profileService.get().subscribe(profile => {
        this.profile = profile;
        this.groupService.get(groupId).subscribe(
          group => {
            this.updateGroup(group, this.profile);
          },
          error => {
            this.errorHandlerService.handleError(error);
          });
      });
    });
  }

  createMatches() {
    if (this.hasMatches()) {
      const confirmRef = this.dialog.open(ConfirmationComponent);
      confirmRef.componentInstance.title = 'Confirm';
      confirmRef.componentInstance.message = 'Are you sure you want to re-create this groups matches? This will assign everyone a new secret santa recipient. This operation cannot be undone.';
      confirmRef.componentInstance.confirmationButtonText = 'Re-Create Matches';
      confirmRef.result.then(confirm => {
        if (confirm) {
          this.groupService.createMatches(this.group.id).subscribe(
            group => {
              this.updateGroup(group, this.profile);
              this.notifyService.default('Matches re-created!');
            },
            error => {
              this.errorHandlerService.handleError(error);
            }
          );
        }
      });
    } else {
      this.groupService.createMatches(this.group.id).subscribe(
        group => {
          this.updateGroup(group, this.profile);
          this.notifyService.default('Matches created!');
        },
        error => {
          this.errorHandlerService.handleError(error);
        }
      );
    }
  }

  hasMatches(): boolean {
    return this.myGroupMember != null && this.myGroupMember.recipientId != null;
  }

  forceShowMatches() {
    if (!this.showMatches) {
      const confirmRef = this.dialog.open(ConfirmationComponent);
      confirmRef.componentInstance.title = 'Confirm';
      confirmRef.componentInstance.message = 'Are you sure you want to reveal all group members\' recipeints to yourself?';
      confirmRef.componentInstance.confirmationButtonText = 'Show Matches';
      confirmRef.result.then(confirm => {
        if (confirm) {
          this.showMatches = !this.showMatches;
        }
      });
    } else {
      this.showMatches = !this.showMatches;
    }
  }

  canForceShowMatches() {
    return this.hasMultipleMembers() && this.hasMatches() && this.myGroupMember.isAdmin;
  }

  forceShowMatchesText(): string {
    if (this.showMatches) {
      return 'Hide Matches';
    } else {
      return 'Show Matches';
    }
  }

  hasMultipleMembers() {
    return this.group.groupMembers && this.group.groupMembers.length > 1;
  }

  copyText(shareLink: string): void {
    this.utilityService.copyText(shareLink);
    this.notifyService.default('Link saved to clipboard.');
  }

  canDeleteGroup(): boolean {
    return this.myGroupMember.isAdmin;
  }

  deleteGroup(groupId: string): void {
    const confirmRef = this.dialog.open(ConfirmationComponent);
    confirmRef.componentInstance.title = 'Confirm';
    confirmRef.componentInstance.message = 'Are you sure you want to delete this group? This operation cannot be undone.';
    confirmRef.componentInstance.confirmationButtonText = 'Delete';
    confirmRef.result.then(confirm => {
      if (confirm) {
        this.groupService.delete(groupId).subscribe(
          response => {
            this.notifyService.default('Group Member Deleted!');
            this.router.navigate(['/']);
          },
          error => {
            this.errorHandlerService.handleError(error);
          }
        );
      }
    });
  }

  onDeletedGroupMember(deletedGroupMember: boolean) {
    if (deletedGroupMember) {
      this.groupService.get(this.group.id).subscribe(
        group => {
          this.updateGroup(group, this.profile);
          this.notifyService.default('Group has been updated');
        },
        error => {
          this.errorHandlerService.handleError(error);
        });
    }
  }

  editMatches() {
    const editMatchesModal = this.dialog.open(EditMatchesComponent);
    editMatchesModal.componentInstance.group = this.utilityService.copyObj<Group>(this.group);
    editMatchesModal.result.then((updateGroup) => {
      if (updateGroup) {
        this.groupService.update(updateGroup).subscribe(
          response => {
            this.updateGroup(updateGroup, this.profile);
            this.notifyService.default('New matches saved!');
          },
          error => {
            this.errorHandlerService.handleError(error);
          }
        );
      }
    });
  }

  private updateGroup(group: Group, profile: Profile): void {
    this.group = group;
    this.group.eventDateDisplay = moment(group.eventDate).format('dddd, MMMM Do YYYY');
    this.group.signUpDeadlineDisplay = moment(group.signUpDeadline).format('dddd, MMMM Do YYYY');
    this.myGroupMember = this.group.groupMembers.find(groupMember => groupMember.userId === profile.id);
    this.shareLink = `${window.location.origin}/new-group-member/${group.id}`;
    this.hasSecretQuestion = this.group.secretQuestion !== undefined &&
      this.group.secretQuestion !== null &&
      this.group.secretQuestion !== '';
  }
}
