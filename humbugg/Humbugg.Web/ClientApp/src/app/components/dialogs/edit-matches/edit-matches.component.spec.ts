import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { EditMatchesComponent } from './edit-matches.component';

describe('EditMatchesComponent', () => {
  let component: EditMatchesComponent;
  let fixture: ComponentFixture<EditMatchesComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ EditMatchesComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(EditMatchesComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
