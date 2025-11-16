import { TestBed } from '@angular/core/testing';

import { GroupMemberService } from './group-member.service';

describe('GroupMemberService', () => {
  beforeEach(() => TestBed.configureTestingModule({}));

  it('should be created', () => {
    const service: GroupMemberService = TestBed.get(GroupMemberService);
    expect(service).toBeTruthy();
  });
});
