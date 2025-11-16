import { NgModule } from '@angular/core';
import { Routes, RouterModule } from '@angular/router';

import { AuthGuardService } from "./services/auth-guard.service";

import { MainNavComponent } from "./components/layout/main-nav/main-nav.component";
import { HomeComponent } from './components/pages/home/home.component';
import { ProfileComponent } from "./components/pages/profile/profile.component";
import { NewGroupComponent } from "./components/pages/new-group/new-group.component";
import { MyGroupsComponent } from './components/pages/my-groups/my-groups.component';
import { GroupDetailsComponent } from './components/pages/group-details/group-details.component';
import { NewGroupMemberComponent } from './components/pages/new-group-member/new-group-member.component';
import { NotFoundComponent } from './components/pages/not-found/not-found.component';

const routes: Routes = [
  {
    path: '',
    component: MainNavComponent,
    children: [
      {
        path: '',
        component: HomeComponent
      },
      {
        path: 'profile',
        component: ProfileComponent,
        canActivate: [AuthGuardService]
      },
      {
        path: 'new-group',
        component: NewGroupComponent,
        canActivate: [AuthGuardService]
      },
      {
        path: 'my-groups',
        component: MyGroupsComponent,
        canActivate: [AuthGuardService]
      },
      {
        path: 'group-details/:id',
        component: GroupDetailsComponent,
        canActivate: [AuthGuardService]
      },
      {
        path: 'new-group-member/:id',
        component: NewGroupMemberComponent,
        canActivate: [AuthGuardService]
      },
      {
        path: '404', 
        component: NotFoundComponent
      },
      {
        path: '**', 
        redirectTo: '/404'
      }
    ]
  }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
