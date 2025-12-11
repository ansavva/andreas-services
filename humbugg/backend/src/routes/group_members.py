from flask import Blueprint, jsonify, request

from src.auth.decorators import requires_auth
from src.config import load_config
from src.repositories.group_member_repository import GroupMemberRepository
from src.repositories.group_repository import GroupRepository
from src.services.member_service import GroupMemberService

config = load_config()
member_repo = GroupMemberRepository(config.mongo_db_name)
group_repo = GroupRepository(config.mongo_db_name)
member_service = GroupMemberService(member_repo, group_repo)

bp = Blueprint('group_members', __name__, url_prefix='/api/groupmember')


@bp.route('/', methods=['GET'])
@requires_auth
def list_members():
  members = member_service.list_for_current_user()
  return jsonify(members)


@bp.route('/<member_id>', methods=['GET'])
@requires_auth
def get_member(member_id: str):
  member = member_service.get(member_id)
  return jsonify(member)


@bp.route('/', methods=['POST'])
@requires_auth
def create_member():
  payload = request.get_json() or {}
  member = member_service.create(payload)
  return jsonify(member), 201


@bp.route('/<member_id>', methods=['PUT'])
@requires_auth
def update_member(member_id: str):
  payload = request.get_json() or {}
  member_service.update(member_id, payload)
  return '', 204


@bp.route('/<member_id>', methods=['DELETE'])
@requires_auth
def delete_member(member_id: str):
  member_service.delete(member_id)
  return '', 204
