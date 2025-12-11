from datetime import datetime
from typing import List

from flask import g

from src.models.errors import HumbuggException
from src.repositories.group_member_repository import GroupMemberRepository
from src.repositories.group_repository import GroupRepository


class GroupMemberService:
  def __init__(self, member_repo: GroupMemberRepository, group_repo: GroupRepository):
    self.member_repo = member_repo
    self.group_repo = group_repo

  @property
  def current_profile_id(self) -> str:
    return g.current_user['profile_id']

  def list_for_current_user(self) -> List[dict]:
    members = self.member_repo.get_by_user(self.current_profile_id)
    return self._sanitize_many(members)

  def get(self, member_id: str) -> dict:
    member = self.member_repo.get(member_id)
    if not member:
      raise HumbuggException('Group member not found.')
    return self._sanitize(member)

  def create(self, payload: dict) -> dict:
    if not payload.get('GroupId'):
      raise HumbuggException('GroupId is required.')
    if self.member_repo.get_by_user_and_group(self.current_profile_id, payload['GroupId']):
      raise HumbuggException('You already joined this group.')
    payload['CreatedDate'] = datetime.utcnow()
    payload['UserId'] = self.current_profile_id
    payload.setdefault('IsAdmin', False)
    payload.setdefault('IsParticipating', True)
    created = self.member_repo.create(payload)
    return created

  def update(self, member_id: str, payload: dict) -> None:
    existing = self.member_repo.get(member_id)
    if not existing:
      raise HumbuggException('Group member not found.')
    my_membership = self.member_repo.get_by_user_and_group(self.current_profile_id, existing['GroupId'])
    if not my_membership:
      raise HumbuggException('Unable to locate your membership for this group.')
    if existing['UserId'] != self.current_profile_id and not my_membership.get('IsAdmin'):
      raise HumbuggException('You do not have permission to update this member.')
    payload.setdefault('_id', existing['_id'])
    self.member_repo.update(member_id, payload)

  def delete(self, member_id: str) -> None:
    existing = self.member_repo.get(member_id)
    if not existing:
      raise HumbuggException('Group member not found.')
    my_membership = self.member_repo.get_by_user_and_group(self.current_profile_id, existing['GroupId'])
    if not my_membership:
      raise HumbuggException('Unable to locate your membership for this group.')
    if not my_membership.get('IsAdmin') and existing.get('RecipientId') != my_membership.get('RecipientId'):
      raise HumbuggException('You cannot delete this member.')
    if my_membership.get('IsAdmin') and existing['UserId'] == self.current_profile_id:
      raise HumbuggException('Admins cannot delete their own membership.')
    self.member_repo.delete(member_id)
    self._clear_matches(existing['GroupId'])

  def _sanitize(self, member: dict) -> dict:
    my_membership = self.member_repo.get_by_user_and_group(self.current_profile_id, member['GroupId'])
    if not my_membership or not my_membership.get('IsAdmin'):
      member['RecipientId'] = None
    return member

  def _sanitize_many(self, members: List[dict]) -> List[dict]:
    my_membership = None
    if members:
      my_membership = self.member_repo.get_by_user_and_group(self.current_profile_id, members[0]['GroupId'])
    result = []
    for member in members:
      sanitized = dict(member)
      if not my_membership or not my_membership.get('IsAdmin'):
        sanitized['RecipientId'] = None
      result.append(sanitized)
    return result

  def _clear_matches(self, group_id: str) -> None:
    members = self.member_repo.get_by_group(group_id)
    for member in members:
      if member.get('RecipientId'):
        self.member_repo.update_recipient(member['Id'], None)
