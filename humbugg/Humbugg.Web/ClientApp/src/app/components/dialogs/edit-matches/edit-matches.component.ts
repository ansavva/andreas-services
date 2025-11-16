import { Component, OnInit, Input } from '@angular/core';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { GroupMember } from '../../../models/groupMember';
import { Group } from 'src/app/models/group';
import { GroupMemberSortable } from 'src/app/models/groupMemberSortable';
import { CdkDragDrop, CdkDragEnd, moveItemInArray } from '@angular/cdk/drag-drop';

@Component({
  selector: 'app-edit-matches',
  templateUrl: './edit-matches.component.html',
  styleUrls: ['./edit-matches.component.scss']
})
export class EditMatchesComponent implements OnInit {
  @Input() group: Group;
  groupMembersSortable: Array<GroupMemberSortable> = [];
  groupMemberRecipientsSortable: Array<GroupMemberSortable> = [];

  constructor(
    public activeModal: NgbActiveModal) {
  }

  ngOnInit() {
    this.group.groupMembers.forEach(groupMember => {
      var groupMemberSortable = new GroupMemberSortable();
      groupMemberSortable.firstName = groupMember.firstName;
      groupMemberSortable.middleName = groupMember.middleName;
      groupMemberSortable.lastName = groupMember.lastName;
      groupMemberSortable.id = groupMember.id;
      this.groupMembersSortable.push(groupMemberSortable);

      var groupRecipientSortable = new GroupMemberSortable();
      var recipient = this.group.groupMembers.find(gm => gm.id == groupMember.recipientId);
      groupRecipientSortable.firstName = recipient.firstName;
      groupRecipientSortable.middleName = recipient.middleName;
      groupRecipientSortable.lastName = recipient.lastName;
      groupRecipientSortable.id = recipient.id;
      this.groupMemberRecipientsSortable.push(groupRecipientSortable);
    });
  }

  save(): void {
    var index = 0;
    this.groupMembersSortable.forEach(groupMember => {
      this.group.groupMembers.find(gm => gm.id == groupMember.id).recipientId = this.groupMemberRecipientsSortable[index].id;
      index++;
    });
    this.activeModal.close(this.group);
  }

  cancel(): void {
    this.activeModal.close();
  }

  dropGroupMember(event: CdkDragDrop<GroupMemberSortable[]>) {
    moveItemInArray(this.groupMembersSortable, event.previousIndex, event.currentIndex);
  }

  dropGroupMemberRecipient(event: CdkDragDrop<GroupMemberSortable[]>) {
    moveItemInArray(this.groupMemberRecipientsSortable, event.previousIndex, event.currentIndex);
  }

  onDragStarted(event: CdkDragEnd): void {
    event.source.element.nativeElement.style.zIndex = "10000 !important";
  }
}
