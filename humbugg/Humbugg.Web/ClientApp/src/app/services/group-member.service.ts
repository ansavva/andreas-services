import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { HttpClient } from '@angular/common/http';

import { GroupMember } from '../models/groupMember';

@Injectable({
  providedIn: 'root'
})
export class GroupMemberService {

  constructor(private httpClient: HttpClient) { }

  getAll(): Observable<Array<GroupMember>> {
    return this.httpClient.get<Array<GroupMember>>(`/api/groupMember`, { withCredentials: true });
  }

  get(groupMemberId: string): Observable<GroupMember> {
    return this.httpClient.get<GroupMember>(`/api/groupMember/${groupMemberId}`, { withCredentials: true })
  }

  create(groupMember: GroupMember): Observable<GroupMember> {
    return this.httpClient.post<GroupMember>(`/api/groupMember`, groupMember, { withCredentials: true });
  }

  update(groupMember: GroupMember): Observable<any> {
    return this.httpClient.put(`/api/groupMember/${groupMember.id}`, groupMember, { withCredentials: true });
  }

  delete(groupMemberId: string): Observable<any> {
    return this.httpClient.delete(`/api/groupMember/${groupMemberId}`, { withCredentials: true });
  }
}
