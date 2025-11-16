import { Component, OnInit, Input, EventEmitter, Output } from '@angular/core';
import { GroupMember } from 'src/app/models/groupMember';
import { Group } from 'src/app/models/group';
import { EditGroupMemberComponent } from '../../dialogs/edit-group-member/edit-group-member.component';
import { ConfirmationComponent } from '../../dialogs/confirmation/confirmation.component';
import { GroupMemberService } from 'src/app/services/group-member.service';
import { NotificationService } from 'src/app/services/notification.service';
import { ErrorHandlerService } from 'src/app/services/error-handler.service';
import { NgbModal } from '@ng-bootstrap/ng-bootstrap';
import { UtilityService } from 'src/app/services/utility.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-group-member-details',
  templateUrl: './group-member-details.component.html',
  styleUrls: ['./group-member-details.component.scss']
})
export class GroupMemberDetailsComponent implements OnInit {
  @Input() groupMember: GroupMember;
  @Input() myGroupMember: GroupMember;
  @Input() group: Group;
  @Input() showMatches: boolean;
  @Input() hasSecretQuestion: boolean;
  @Output() deletedGroupMember = new EventEmitter<boolean>();

  constructor(
    public groupMemberService: GroupMemberService,
    public errorHandlerService: ErrorHandlerService,
    public notifyService: NotificationService,
    public router: Router,
    private modalService: NgbModal,
    private utilityService: UtilityService
  ) { }

  ngOnInit() {
  }

  isMyGroupMember(): boolean {
    return this.groupMember.id == this.myGroupMember.id;
  }

  hasMatch(): boolean {
    return this.groupMember.recipientId !== null &&
           this.groupMember.recipientId !== '' &&
           this.match() !== null &&
           (this.myGroupMember.recipientId === this.groupMember.recipientId || this.showMatches);
  }

  match(): GroupMember {
    return this.group.groupMembers.find(groupMember => groupMember.id === this.groupMember.recipientId);
  }

  canEditGroupMember(): boolean {
    return this.myGroupMember.isAdmin || this.myGroupMember.userId === this.groupMember.userId;
  }

  editGroupMember(): void {
    const editGroupMemberModal = this.modalService.open(EditGroupMemberComponent);
    editGroupMemberModal.componentInstance.group = this.group;
    editGroupMemberModal.componentInstance.myGroupMember = this.group;
    editGroupMemberModal.componentInstance.groupMember = this.utilityService.copyObj<GroupMember>(this.groupMember);
    editGroupMemberModal.result.then((updatedGroupMember) => {
      if (updatedGroupMember) {
        this.groupMember = updatedGroupMember;
      }
    });
  }

  canDeleteGroupMember(): boolean {
    if (this.myGroupMember.isAdmin && this.myGroupMember.userId !== this.groupMember.userId) {
      return true;
    } else if (!this.myGroupMember.isAdmin && this.myGroupMember.userId === this.groupMember.userId) {
      return true;
    } else {
      return false;
    }
  }

  deleteGroupMember(): void {
    var message = 'Are you sure you want to delete this group member? This operation will remove all created matches this group.';
    var buttonText = 'Delete';
    if (this.isMyGroupMember()) {
      message = 'Are you sure you want to leave this group? This operation will remove all created matches for this group.';
      buttonText = 'Leave';
    }
    const confirmRef = this.modalService.open(ConfirmationComponent);
    confirmRef.componentInstance.title = 'Confirm';
    confirmRef.componentInstance.message = message;
    confirmRef.componentInstance.confirmationButtonText = buttonText;
    confirmRef.result.then(confirm => {
      if (confirm) {
        this.groupMemberService.delete(this.groupMember.id).subscribe(
          response => {
            if (this.isMyGroupMember()) {
              this.router.navigate(['/']);
            } else {
              this.group.groupMembers.splice(this.group.groupMembers.indexOf(this.groupMember), 1);
              this.notifyService.default('Group member has been deleted');
              this.deletedGroupMember.emit(true);
            }
          },
          error => {
            this.errorHandlerService.handleError(error);
          }
        );
      }
    });
  }

  hasAddress(): boolean {
    if (this.groupMember.address1) return true;
    return false;
  }

  addressDisplay(): string {
    if (this.groupMember.address2) {
      return `${this.groupMember.address1} ${this.groupMember.address2} ${this.groupMember.city} ${this.groupMember.state} ${this.groupMember.postalCode}`;
    }
    return `${this.groupMember.address1} ${this.groupMember.city} ${this.groupMember.state} ${this.groupMember.postalCode}`;
  }

  deleteGroupMemberText(): string {
    if (this.isMyGroupMember()) {
      return 'Leave';
    }
    return 'Delete';
  }
}
