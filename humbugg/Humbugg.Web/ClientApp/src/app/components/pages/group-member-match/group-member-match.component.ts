import { Component, Input, OnInit } from '@angular/core';
import { Group } from 'src/app/models/group';
import { GroupMember } from 'src/app/models/groupMember';

@Component({
  selector: '[app-group-member-match]',
  templateUrl: './group-member-match.component.html',
  styleUrls: ['./group-member-match.component.scss']
})
export class GroupMemberMatchComponent implements OnInit {
  @Input() groupMember: GroupMember;
  @Input() group: Group;
  @Input() hasSecretQuestion: boolean;
  
  constructor() { }

  ngOnInit() {
  }

  hasMatch(): boolean {
    return this.groupMember.recipientId !== null &&
           this.groupMember.recipientId !== '' &&
           this.match() !== null;
  }

  match(): GroupMember {
    return this.group.groupMembers.find(groupMember => groupMember.id === this.groupMember.recipientId);
  }
}
