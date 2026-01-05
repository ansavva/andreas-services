from flask import Blueprint, request, jsonify

from src.repositories.db.child_profile_repo import ChildProfileRepo
from src.utils.logging.error_logging import log_error

child_profile_controller = Blueprint("child_profile_controller", __name__)
child_profile_repo = ChildProfileRepo()

@child_profile_controller.route("/project/<string:project_id>", methods=["GET"])
def get_child_profile_by_project(project_id):
    """Get child profile for a specific project"""
    try:
        profile = child_profile_repo.get_by_project_id(project_id)
        if not profile:
            return jsonify({"error": "Child profile not found"}), 404
        return jsonify(profile.to_dict()), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@child_profile_controller.route("/project/<string:project_id>", methods=["PUT"])
def update_child_profile_by_project(project_id):
    """Update child profile by project ID"""
    try:
        # Get the profile first to get the profile_id
        profile = child_profile_repo.get_by_project_id(project_id)
        if not profile:
            return jsonify({"error": "Child profile not found"}), 404

        data = request.get_json()

        # Validate age if provided
        child_age = data.get("child_age")
        if child_age is not None:
            if not isinstance(child_age, int) or child_age < 0 or child_age > 12:
                return jsonify({"error": "Child age must be between 0 and 12"}), 400

        updated_profile = child_profile_repo.update(
            profile_id=profile.id,
            child_name=data.get("child_name"),
            child_age=child_age,
            photo_ids=data.get("photo_ids")
        )
        return jsonify(updated_profile.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@child_profile_controller.route("/<string:profile_id>", methods=["GET"])
def get_child_profile(profile_id):
    """Get a specific child profile by ID"""
    try:
        profile = child_profile_repo.get_by_id(profile_id)
        return jsonify(profile.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@child_profile_controller.route("", methods=["POST"])
def create_child_profile():
    """Create a new child profile"""
    try:
        data = request.get_json()
        project_id = data.get("project_id")
        child_name = data.get("child_name")
        child_age = data.get("child_age")
        consent_given = data.get("consent_given")
        photo_ids = data.get("photo_ids", [])

        # Validation
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not child_name:
            return jsonify({"error": "Child name is required"}), 400
        if child_age is None:
            return jsonify({"error": "Child age is required"}), 400
        if not isinstance(child_age, int) or child_age < 0 or child_age > 12:
            return jsonify({"error": "Child age must be between 0 and 12"}), 400
        if not consent_given:
            return jsonify({"error": "Consent is required"}), 400

        profile = child_profile_repo.create(
            project_id=project_id,
            child_name=child_name,
            child_age=child_age,
            consent_given=consent_given,
            photo_ids=photo_ids
        )
        return jsonify(profile.to_dict()), 201
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@child_profile_controller.route("/<string:profile_id>", methods=["PUT"])
def update_child_profile(profile_id):
    """Update child profile"""
    try:
        data = request.get_json()

        # Validate age if provided
        child_age = data.get("child_age")
        if child_age is not None:
            if not isinstance(child_age, int) or child_age < 0 or child_age > 12:
                return jsonify({"error": "Child age must be between 0 and 12"}), 400

        profile = child_profile_repo.update(
            profile_id=profile_id,
            child_name=data.get("child_name"),
            child_age=child_age,
            photo_ids=data.get("photo_ids")
        )
        return jsonify(profile.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@child_profile_controller.route("/<string:profile_id>", methods=["DELETE"])
def delete_child_profile(profile_id):
    """Delete a child profile"""
    try:
        child_profile_repo.delete(profile_id)
        return jsonify({"message": "Child profile deleted successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
