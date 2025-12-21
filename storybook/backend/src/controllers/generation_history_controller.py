from flask import Blueprint, request, jsonify

from src.data.generation_history_repo import GenerationHistoryRepo
from src.data.user_profile_repo import UserProfileRepo

generation_history_controller = Blueprint("generation_history_controller", __name__)
generation_history_repo = GenerationHistoryRepo()
user_profile_repo = UserProfileRepo()

@generation_history_controller.route('/create', methods=['POST'])
def create_history():
    """
    Create a new generation history entry

    Request body:
        {
            "project_id": "uuid",
            "prompt": "the prompt text",
            "image_ids": ["image_id1", "image_id2", ...]
        }
    """
    try:
        data = request.get_json()
        project_id = data.get("project_id")
        prompt = data.get("prompt")
        image_ids = data.get("image_ids", [])

        if not project_id:
            return jsonify({"error": "project_id is required"}), 400
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        history = generation_history_repo.create(project_id, prompt, image_ids)
        profile = user_profile_repo.get_by_id(history.user_id)

        return jsonify({
            "id": history.id,
            "project_id": history.project_id,
            "user_id": history.user_id,
            "prompt": history.prompt,
            "image_ids": history.image_ids,
            "created_at": history.created_at.isoformat() if history.created_at else None,
            "user_profile": {
                "display_name": profile.display_name if profile else None,
                "profile_image_id": profile.profile_image_id if profile else None
            }
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@generation_history_controller.route('/<string:history_id>', methods=['GET'])
def get_history(history_id: str):
    """
    Get a generation history entry by ID
    """
    try:
        history = generation_history_repo.get_by_id(history_id)

        return jsonify({
            "id": history.id,
            "project_id": history.project_id,
            "user_id": history.user_id,
            "prompt": history.prompt,
            "image_ids": history.image_ids,
            "created_at": history.created_at.isoformat() if history.created_at else None
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@generation_history_controller.route('/project/<string:project_id>', methods=['GET'])
def list_history_by_project(project_id: str):
    """
    List all generation history entries for a project (newest first)
    Enriched with user profile information
    """
    try:
        histories = generation_history_repo.list_by_project(project_id)

        # Collect unique user IDs
        user_ids = list(set(h.user_id for h in histories))

        # Fetch user profiles in bulk
        user_profiles = user_profile_repo.get_multiple(user_ids)

        # Build response with enriched user data
        enriched_histories = []
        for h in histories:
            profile = user_profiles.get(h.user_id)

            enriched_histories.append({
                "id": h.id,
                "project_id": h.project_id,
                "user_id": h.user_id,
                "prompt": h.prompt,
                "image_ids": h.image_ids,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "user_profile": {
                    "display_name": profile.display_name if profile else None,
                    "profile_image_id": profile.profile_image_id if profile else None
                }
            })

        return jsonify({"histories": enriched_histories}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@generation_history_controller.route('/<string:history_id>', methods=['DELETE'])
def delete_history(history_id: str):
    """
    Delete a generation history entry
    """
    try:
        generation_history_repo.delete(history_id)
        return jsonify({"message": "Generation history deleted successfully"}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
