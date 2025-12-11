import axios, { AxiosRequestConfig } from 'axios';

import { Group, GroupMember, Profile } from '../types';
import { mapGroup, mapGroupMember, mapProfile } from './transformers';

const API_PREFIX = '/api';

export interface ApiRequestOptions extends AxiosRequestConfig {
  token?: string | null;
  baseUrl: string;
}

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');

const buildUrl = (baseUrl: string, path: string) => {
  const prefix = path.startsWith('/') ? path : `/${path}`;
  return `${trimTrailingSlash(baseUrl)}${API_PREFIX}${prefix}`;
};

async function request<T>(path: string, { baseUrl, token, ...config }: ApiRequestOptions): Promise<T> {
  if (!baseUrl) {
    throw new Error('Missing API base URL.');
  }
  const response = await axios.request<T>({
    url: buildUrl(baseUrl, path),
    headers: {
      'Content-Type': 'application/json',
      ...(config.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    ...config
  });
  return response.data;
}

export async function fetchProfile(options: ApiRequestOptions): Promise<Profile> {
  const payload = await request('/profile', options);
  return mapProfile(payload);
}

export async function fetchGroups(options: ApiRequestOptions): Promise<Group[]> {
  const payload = await request<any[]>('/group', options);
  return payload.map(mapGroup);
}

export async function fetchGroup(groupId: string, options: ApiRequestOptions): Promise<Group> {
  const payload = await request(`/group/${groupId}`, options);
  return mapGroup(payload);
}

export interface GroupPayload {
  Name: string;
  Description?: string;
  SecretQuestion?: string;
  SecretQuestionAnswer?: string;
  SignUpDeadline?: string;
  EventDate?: string;
  SpendingLimit?: number;
  GroupRules?: any[];
  GroupMembers: GroupMemberPayload[];
}

export interface GroupMemberPayload {
  Id?: string;
  GroupId?: string;
  UserId?: string;
  IsAdmin?: boolean;
  IsParticipating?: boolean;
  RecipientId?: string | null;
  FirstName?: string;
  MiddleName?: string;
  LastName?: string;
  Address1?: string;
  Address2?: string;
  City?: string;
  State?: string;
  PostalCode?: string;
  GiftSuggestionsDescription?: string;
  GiftAvoidancesDescription?: string;
  SecretQuestionAnswer?: string;
}

export async function createGroup(payload: GroupPayload, options: ApiRequestOptions): Promise<Group> {
  const response = await request('/group', {
    ...options,
    method: 'POST',
    data: payload
  });
  return mapGroup(response);
}

export async function createGroupMember(payload: GroupMemberPayload, options: ApiRequestOptions): Promise<GroupMember> {
  const response = await request('/groupmember', {
    ...options,
    method: 'POST',
    data: payload
  });
  return mapGroupMember(response);
}

export async function deleteGroupMember(groupMemberId: string, options: ApiRequestOptions): Promise<void> {
  await request(`/groupmember/${groupMemberId}`, {
    ...options,
    method: 'DELETE'
  });
}

export async function deleteGroup(groupId: string, options: ApiRequestOptions): Promise<void> {
  await request(`/group/${groupId}`, {
    ...options,
    method: 'DELETE'
  });
}

export async function triggerMatches(groupId: string, options: ApiRequestOptions): Promise<Group> {
  const response = await request(`/group/createMatches/${groupId}`, {
    ...options,
    method: 'GET'
  });
  return mapGroup(response);
}
