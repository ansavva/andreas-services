import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { GroupMemberDetailsComponent } from './group-member-details.component';

describe('GroupMemberDetailsComponent', () => {
  let component: GroupMemberDetailsComponent;
  let fixture: ComponentFixture<GroupMemberDetailsComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ GroupMemberDetailsComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(GroupMemberDetailsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
