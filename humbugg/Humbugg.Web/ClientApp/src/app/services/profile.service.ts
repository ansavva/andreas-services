import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { HttpClient } from '@angular/common/http';

import { Profile } from '../models/profile';

@Injectable({
  providedIn: 'root'
})
export class ProfileService {

  constructor(private httpClient: HttpClient) { }

  get(): Observable<Profile> {
    return this.httpClient.get<Profile>(`/api/profile`, { withCredentials: true });
  }

  update(profile: Profile): Observable<any> {
    return this.httpClient.put<Profile>(`/api/profile/${profile.id}`, profile, { withCredentials: true });
  }
}
