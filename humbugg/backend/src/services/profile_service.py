from datetime import datetime

from flask import g

from src.models.errors import HumbuggException
from src.repositories.profile_repository import ProfileRepository


class ProfileService:
  def __init__(self, profile_repo: ProfileRepository):
    self.profile_repo = profile_repo

  @property
  def current_profile_id(self) -> str:
    return g.current_user['profile_id']

  def get_current(self) -> dict:
    profile = self.profile_repo.get(self.current_profile_id)
    if not profile:
      raise HumbuggException('Profile not found.')
    return profile

  def get(self, profile_id: str) -> dict:
    profile = self.profile_repo.get(profile_id)
    if not profile:
      raise HumbuggException('Profile not found.')
    return profile

  def create(self, payload: dict) -> dict:
    payload['CreatedDate'] = datetime.utcnow()
    return self.profile_repo.create(payload)

  def update(self, profile_id: str, payload: dict) -> None:
    if not self.profile_repo.get(profile_id):
      raise HumbuggException('Profile not found.')
    self.profile_repo.update(profile_id, payload)

  def delete(self, profile_id: str) -> None:
    if not self.profile_repo.get(profile_id):
      raise HumbuggException('Profile not found.')
    self.profile_repo.delete(profile_id)
