import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { GroupMemberMatchComponent } from './group-member-match.component';

describe('GroupMemberMatchComponent', () => {
  let component: GroupMemberMatchComponent;
  let fixture: ComponentFixture<GroupMemberMatchComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ GroupMemberMatchComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(GroupMemberMatchComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
