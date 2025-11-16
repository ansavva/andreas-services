import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { EditGroupMemberComponent } from './edit-group-member.component';

describe('GroupMemberDetailsComponent', () => {
  let component: EditGroupMemberComponent;
  let fixture: ComponentFixture<EditGroupMemberComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ EditGroupMemberComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(EditGroupMemberComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
