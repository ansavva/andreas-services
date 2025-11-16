import { Component, OnInit } from '@angular/core';
import { Router, CanActivate } from '@angular/router';
import * as moment from 'moment';

import { Group } from '../../../models/group';
import { GroupService } from '../../../services/group.service';
import { ErrorHandlerService } from 'src/app/services/error-handler.service';

@Component({
  selector: 'app-my-groups',
  templateUrl: './my-groups.component.html',
  styleUrls: ['./my-groups.component.scss']
})
export class MyGroupsComponent implements OnInit {
  groups: Array<Group> = new Array<Group>();

  constructor(
    private groupService: GroupService,
    private errorHandlerService: ErrorHandlerService,
    public router: Router) { }

  ngOnInit() {
    this.groupService.getAll().subscribe(
      groups => {
        this.groups = groups;
        this.groups.forEach(group => {
          group.eventDateDisplay = moment(group.eventDate).format('LLLL');
        });
      },
      error => {
        this.errorHandlerService.handleError(error);
      });
  }

  goToGroup(groupId: number) : void {
    this.router.navigate([`group-details/${groupId}`]);
  }
}
