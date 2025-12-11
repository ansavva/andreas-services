from flask import Blueprint, jsonify, request

from src.auth.decorators import requires_auth
from src.config import load_config
from src.repositories.profile_repository import ProfileRepository
from src.services.profile_service import ProfileService

config = load_config()
profile_repo = ProfileRepository(config.mongo_db_name)
profile_service = ProfileService(profile_repo)

bp = Blueprint('profiles', __name__, url_prefix='/api/profile')


@bp.route('/', methods=['GET'])
@requires_auth
def get_current_profile():
  profile = profile_service.get_current()
  return jsonify(profile)


@bp.route('/<profile_id>', methods=['GET'])
@requires_auth
def get_profile(profile_id: str):
  profile = profile_service.get(profile_id)
  return jsonify(profile)


@bp.route('/', methods=['POST'])
@requires_auth
def create_profile():
  payload = request.get_json() or {}
  profile = profile_service.create(payload)
  return jsonify(profile), 201


@bp.route('/<profile_id>', methods=['PUT'])
@requires_auth
def update_profile(profile_id: str):
  payload = request.get_json() or {}
  profile_service.update(profile_id, payload)
  return '', 204


@bp.route('/<profile_id>', methods=['DELETE'])
@requires_auth
def delete_profile(profile_id: str):
  profile_service.delete(profile_id)
  return '', 204
