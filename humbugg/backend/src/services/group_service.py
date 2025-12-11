from datetime import datetime
from typing import List, Optional

from flask import g

from src.models.errors import HumbuggException
from src.repositories.group_member_repository import GroupMemberRepository
from src.repositories.group_repository import GroupRepository
from src.utils.matching import assign_recipients


class GroupService:
  def __init__(self, group_repo: GroupRepository, member_repo: GroupMemberRepository):
    self.group_repo = group_repo
    self.member_repo = member_repo

  @property
  def current_user_id(self) -> str:
    return g.current_user['profile_id']

  def list(self) -> List[dict]:
    memberships = self.member_repo.get_by_user(self.current_user_id)
    groups = []
    for membership in memberships:
      group = self.group_repo.get(membership['GroupId'])
      if not group:
        continue
      group['GroupMembers'] = self.member_repo.get_by_group(membership['GroupId'])
      groups.append(group)
    return groups

  def get(self, group_id: str) -> dict:
    group = self.group_repo.get(group_id)
    if not group:
      raise HumbuggException('Group not found.')
    group['GroupMembers'] = self.member_repo.get_by_group(group_id)
    self._sanitize_recipients(group['GroupMembers'])
    return group

  def create(self, payload: dict) -> dict:
    now = datetime.utcnow()
    payload['CreatedDate'] = now
    group_members = payload.pop('GroupMembers', [])
    group = self.group_repo.create(payload)
    docs = []
    for member in group_members:
      member['GroupId'] = group['_id']
      member['CreatedDate'] = now
      member['IsAdmin'] = True
      docs.append(member)
    if docs:
      self.member_repo.create_many(docs)
    group['GroupMembers'] = docs
    return group

  def update(self, group_id: str, payload: dict) -> None:
    admin_membership = self.member_repo.get_by_user_and_group(self.current_user_id, group_id)
    if not admin_membership or not admin_membership.get('IsAdmin'):
      raise HumbuggException('Unauthorized to update group.')
    self.group_repo.update(group_id, payload)
    for member in payload.get('GroupMembers', []):
      if 'Id' in member:
        self.member_repo.update(member['Id'], member)

  def delete(self, group_id: str) -> None:
    admin_membership = self.member_repo.get_by_user_and_group(self.current_user_id, group_id)
    if not admin_membership or not admin_membership.get('IsAdmin'):
      raise HumbuggException('Unauthorized to delete group.')
    self.member_repo.delete_by_group(group_id)
    self.group_repo.delete(group_id)

  def create_matches(self, group_id: str) -> dict:
    admin_membership = self.member_repo.get_by_user_and_group(self.current_user_id, group_id)
    if not admin_membership or not admin_membership.get('IsAdmin'):
      raise HumbuggException('Unauthorized to create matches.')
    members = self.member_repo.get_by_group(group_id)
    assign_recipients(members, self.member_repo.update_recipient)
    return self.get(group_id)

  def _sanitize_recipients(self, members: List[dict]) -> None:
    admin_membership = None
    if members:
      admin_membership = self.member_repo.get_by_user_and_group(self.current_user_id, members[0]['GroupId'])
    for member in members:
      if not admin_membership or not admin_membership.get('IsAdmin'):
        member['RecipientId'] = None
