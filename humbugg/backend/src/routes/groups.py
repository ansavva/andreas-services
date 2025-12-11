from flask import Blueprint, jsonify, request

from src.auth.decorators import requires_auth
from src.config import load_config
from src.extensions import init_mongo
from src.repositories.group_member_repository import GroupMemberRepository
from src.repositories.group_repository import GroupRepository
from src.services.group_service import GroupService

config = load_config()
init_mongo(config.mongo_uri)

group_repo = GroupRepository(config.mongo_db_name)
member_repo = GroupMemberRepository(config.mongo_db_name)
group_service = GroupService(group_repo, member_repo)

bp = Blueprint('groups', __name__, url_prefix='/api/group')


@bp.route('/', methods=['GET'])
@requires_auth
def list_groups():
  groups = group_service.list()
  return jsonify(groups)


@bp.route('/<group_id>', methods=['GET'])
@requires_auth
def get_group(group_id: str):
  group = group_service.get(group_id)
  return jsonify(group)


@bp.route('/', methods=['POST'])
@requires_auth
def create_group():
  payload = request.get_json() or {}
  created = group_service.create(payload)
  return jsonify(created), 201


@bp.route('/<group_id>', methods=['PUT'])
@requires_auth
def update_group(group_id: str):
  payload = request.get_json() or {}
  group_service.update(group_id, payload)
  return '', 204


@bp.route('/<group_id>', methods=['DELETE'])
@requires_auth
def delete_group(group_id: str):
  group_service.delete(group_id)
  return '', 204


@bp.route('/createMatches/<group_id>', methods=['GET'])
@requires_auth
def create_matches(group_id: str):
  result = group_service.create_matches(group_id)
  return jsonify(result)
