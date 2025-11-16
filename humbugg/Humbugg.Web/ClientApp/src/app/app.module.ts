import { HTTP_INTERCEPTORS, HttpClientModule } from '@angular/common/http';
import { APP_INITIALIZER, NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { FlexLayoutModule } from '@angular/flex-layout';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';

import { AppRoutingModule } from './app-routing.module';

import { NgbModule } from '@ng-bootstrap/ng-bootstrap';

import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { library } from '@fortawesome/fontawesome-svg-core';
import { 
  faEdit as fasEdit, 
  faTrashAlt as fasTrashAlt, 
  faCalendarAlt as fasCalendarAlt, 
  faQuestionCircle as fasQuestionCircle,
  faEllipsisV as fasEllipsisV
} from '@fortawesome/free-solid-svg-icons';
import { 
  faEdit, 
  faTrashAlt, 
  faCalendarAlt, 
  faQuestionCircle
} from '@fortawesome/free-regular-svg-icons';
import { faFacebookSquare, faGoogle } from '@fortawesome/free-brands-svg-icons';

import { NotifierModule, NotifierOptions } from 'angular-notifier';

import { checkIfUserIsAuthenticated } from './checkIfUserIsAuthenticated';
import { DeAuthInterceptor } from './deAuth.interceptor';

import { AuthService } from './services/auth.service';
import { AuthGuardService } from './services/auth-guard.service';

import { AppComponent } from './app.component';
import { HomeComponent } from './components/pages/home/home.component';
import { ProfileComponent } from './components/pages/profile/profile.component';
import { NewGroupComponent } from './components/pages/new-group/new-group.component';
import { PageTitleComponent } from './components/layout/page-title/page-title.component';
import { HelpComponent } from './components/help/help.component';
import { ConfettiComponent } from './components/confetti/confetti.component';
import { MyGroupsComponent } from './components/pages/my-groups/my-groups.component';
import { GroupDetailsComponent } from './components/pages/group-details/group-details.component';
import { NewGroupMemberComponent } from './components/pages/new-group-member/new-group-member.component';
import { EditGroupMemberComponent } from './components/dialogs/edit-group-member/edit-group-member.component';
import { LayoutModule } from '@angular/cdk/layout';
import { DragDropModule } from '@angular/cdk/drag-drop';
import { MainNavComponent } from './components/layout/main-nav/main-nav.component';
import { ConfirmationComponent } from './components/dialogs/confirmation/confirmation.component';
import { NotFoundComponent } from './components/pages/not-found/not-found.component';
import { GroupMemberDetailsComponent } from './components/pages/group-member-details/group-member-details.component';
import { GroupMemberMatchComponent } from './components/pages/group-member-match/group-member-match.component';
import { EditMatchesComponent } from './components/dialogs/edit-matches/edit-matches.component';

const notifierDefaultOptions: NotifierOptions = {
  position: {
      horizontal: {
          position: 'middle',
          distance: 12
      },
      vertical: {
          position: 'bottom',
          distance: 12,
          gap: 10
      }
  },
  theme: 'material',
  behaviour: {
      autoHide: 5000,
      onClick: false,
      onMouseover: 'pauseAutoHide',
      showDismissButton: true,
      stacking: 4
  },
  animations: {
      enabled: true,
      show: {
          preset: 'slide',
          speed: 300,
          easing: 'ease'
      },
      hide: {
          preset: 'fade',
          speed: 300,
          easing: 'ease',
          offset: 50
      },
      shift: {
          speed: 300,
          easing: 'ease'
      },
      overlap: 150
  }
};

@NgModule({
  declarations: [
    AppComponent,
    HomeComponent,
    ProfileComponent,
    NewGroupComponent,
    PageTitleComponent,
    HelpComponent,
    ConfettiComponent,
    MyGroupsComponent,
    GroupDetailsComponent,
    NewGroupMemberComponent,
    EditGroupMemberComponent,
    MainNavComponent,
    ConfirmationComponent,
    NotFoundComponent,
    GroupMemberDetailsComponent,
    GroupMemberMatchComponent,
    EditMatchesComponent
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    HttpClientModule,
    FormsModule,
    ReactiveFormsModule,
    BrowserAnimationsModule,
    FlexLayoutModule,
    FontAwesomeModule,
    NotifierModule.withConfig(notifierDefaultOptions),
    LayoutModule,
    DragDropModule,
    NgbModule
  ],
  entryComponents: [
    EditGroupMemberComponent,
    ConfirmationComponent,
    EditMatchesComponent
  ],
  providers: [
    { provide: HTTP_INTERCEPTORS, useClass: DeAuthInterceptor, multi: true },
    { provide: APP_INITIALIZER, useFactory: checkIfUserIsAuthenticated, multi: true, deps: [AuthService]},
    AuthGuardService
  ],
  bootstrap: [AppComponent]
})
export class AppModule {
  constructor() {
    library.add(
      faEdit,
      fasEdit,
      faTrashAlt,
      fasTrashAlt,
      faFacebookSquare,
      faGoogle,
      fasCalendarAlt,
      faCalendarAlt,
      fasQuestionCircle,
      faQuestionCircle,
      fasEllipsisV
    );
  }
}
