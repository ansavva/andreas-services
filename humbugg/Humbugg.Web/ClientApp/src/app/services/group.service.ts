import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { HttpClient } from '@angular/common/http';

import { Group } from '../models/group';

@Injectable({
  providedIn: 'root'
})
export class GroupService {

  constructor(private httpClient: HttpClient) { }

  getAll(): Observable<Array<Group>> {
    return this.httpClient.get<Array<Group>>(`/api/group`, { withCredentials: true });
  }

  get(groupId: string): Observable<Group> {
    return this.httpClient.get<Group>(`/api/group/${groupId}`, { withCredentials: true })
  }

  createMatches(groupId: string): Observable<Group> {
    return this.httpClient.get<Group>(`/api/group/createMatches/${groupId}`, { withCredentials: true })
  }

  create(group: Group): Observable<Group> {
    return this.httpClient.post<Group>(`/api/group`, group, { withCredentials: true });
  }

  update(group: Group): Observable<any> {
    return this.httpClient.put<Group>(`/api/group/${group.id}`, group, { withCredentials: true });
  }

  delete(groupId: string): Observable<any> {
    return this.httpClient.delete(`/api/group/${groupId}`, { withCredentials: true });
  }
}
