import { Component, OnInit, Input } from '@angular/core';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';

import { GroupMemberService } from '../../../services/group-member.service';
import { NotificationService } from '../../../services/notification.service';
import { GroupMember } from '../../../models/groupMember';
import { Group } from 'src/app/models/group';
import { ErrorHandlerService } from 'src/app/services/error-handler.service';

@Component({
  selector: 'app-edit-group-member',
  templateUrl: './edit-group-member.component.html',
  styleUrls: ['./edit-group-member.component.scss']
})
export class EditGroupMemberComponent implements OnInit {
  @Input() groupMember: GroupMember;
  @Input() myGroupMember: GroupMember;
  @Input() group: Group;
  
  constructor(
    private groupMemberService: GroupMemberService,
    private notifyService: NotificationService,
    private errorHandlerService: ErrorHandlerService,
    public activeModal: NgbActiveModal) {
  }

  ngOnInit() {
  }

  save(): void {
    this.groupMemberService.update(this.groupMember).subscribe(
      response => {
        this.notifyService.success('Group member has been updated.');
        this.activeModal.close(this.groupMember);
      },
      error => {
        this.errorHandlerService.handleError(error);
        this.activeModal.close();
      });
  }

  cancel(): void {
    this.activeModal.close();
  }

  hasMiddleName(): boolean {
    return this.groupMember.middleName != null;
  }

  hasSecretQuestion(): boolean {
    return this.group.secretQuestion != null;
  }
}
