from flask import Blueprint, request, jsonify

from src.data.story_project_repo import StoryProjectRepo
from src.utils.error_logging import log_error

story_project_controller = Blueprint("story_project_controller", __name__)
story_project_repo = StoryProjectRepo()

@story_project_controller.route("", methods=["GET"])
def get_story_projects():
    """Get all story projects for the current user"""
    try:
        projects = story_project_repo.get_projects()
        project_list = [project.to_dict() for project in projects]
        return jsonify(project_list), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@story_project_controller.route("/<string:project_id>", methods=["GET"])
def get_story_project(project_id):
    """Get a specific story project by ID"""
    try:
        project = story_project_repo.get_project(project_id)
        return jsonify(project.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@story_project_controller.route("", methods=["POST"])
def create_story_project():
    """Create a new story project"""
    try:
        data = request.get_json()
        name = data.get("name")

        if not name:
            return jsonify({"error": "Project name is required"}), 400

        project = story_project_repo.create_project(name)
        return jsonify(project.to_dict()), 201
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@story_project_controller.route("/<string:project_id>/status", methods=["PUT"])
def update_project_status(project_id):
    """Update project status"""
    try:
        data = request.get_json()
        status = data.get("status")

        if not status:
            return jsonify({"error": "Status is required"}), 400

        project = story_project_repo.update_status(project_id, status)
        return jsonify(project.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@story_project_controller.route("/<string:project_id>", methods=["PUT"])
def update_story_project(project_id):
    """Update story project fields"""
    try:
        data = request.get_json()

        project = story_project_repo.update_project(
            project_id=project_id,
            name=data.get("name"),
            child_profile_id=data.get("child_profile_id"),
            character_bible_id=data.get("character_bible_id"),
            story_state_id=data.get("story_state_id")
        )
        return jsonify(project.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@story_project_controller.route("/<string:project_id>", methods=["DELETE"])
def delete_story_project(project_id):
    """Delete a story project and all associated data"""
    try:
        story_project_repo.delete_project(project_id)
        return jsonify({"message": "Project deleted successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
