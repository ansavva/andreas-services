import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { NewGroupMemberComponent } from './new-group-member.component';

describe('NewGroupMemberComponent', () => {
  let component: NewGroupMemberComponent;
  let fixture: ComponentFixture<NewGroupMemberComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ NewGroupMemberComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(NewGroupMemberComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
