from flask import Blueprint, request, jsonify

from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.repositories.db.image_repo import ImageRepo
from src.repositories.db.user_profile_repo import UserProfileRepo
from src.services.model_service import ModelService

generation_history_controller = Blueprint("generation_history_controller", __name__)
generation_history_repo = GenerationHistoryRepo()
user_profile_repo = UserProfileRepo()
image_repo = ImageRepo()
model_service = ModelService()


def _build_image_processing_map(image_ids):
    ids = [image_id for image_id in (image_ids or []) if image_id]
    if not ids:
        return {}
    images = image_repo.get_images_by_ids(ids)
    return {img.id: img.processing for img in images}

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
        reference_image_ids = data.get("reference_image_ids")
        include_subject_description = data.get("include_subject_description")

        if not project_id:
            return jsonify({"error": "project_id is required"}), 400
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        draft = generation_history_repo.get_draft_by_project(project_id)
        if draft:
            history = generation_history_repo.finalize_draft(
                draft.id,
                prompt,
                image_ids,
                reference_image_ids,
                include_subject_description,
            )
        else:
            history = generation_history_repo.create(
                project_id,
                prompt,
                image_ids,
                reference_image_ids,
                include_subject_description=include_subject_description,
            )
        profile = user_profile_repo.get_by_id(history.user_id)
        return jsonify({
            "id": history.id,
            "project_id": history.project_id,
            "user_id": history.user_id,
            "prompt": history.prompt,
            "image_ids": history.image_ids,
            "reference_image_ids": history.reference_image_ids or [],
            "status": history.status,
            "prediction_id": history.prediction_id,
            "provider": history.provider,
            "error_message": history.error_message,
            "include_subject_description": history.include_subject_description,
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
            "reference_image_ids": history.reference_image_ids or [],
            "status": history.status,
            "prediction_id": history.prediction_id,
            "provider": history.provider,
            "error_message": history.error_message,
            "include_subject_description": history.include_subject_description,
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
        all_image_ids = []
        for h in histories:
            all_image_ids.extend(h.image_ids or [])
            all_image_ids.extend(h.reference_image_ids or [])

        for h in histories:
            profile = user_profiles.get(h.user_id)
            enriched_histories.append({
                "id": h.id,
                "project_id": h.project_id,
                "user_id": h.user_id,
                "prompt": h.prompt,
                "image_ids": h.image_ids,
                "reference_image_ids": h.reference_image_ids or [],
                "status": h.status,
                "prediction_id": h.prediction_id,
                "provider": h.provider,
                "error_message": h.error_message,
                "include_subject_description": h.include_subject_description,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "user_profile": {
                    "display_name": profile.display_name if profile else None,
                    "profile_image_id": profile.profile_image_id if profile else None
                }
            })

        return jsonify({"histories": enriched_histories}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@generation_history_controller.route('/draft/<string:project_id>', methods=['GET'])
def get_draft_history(project_id: str):
    """
    Get the draft generation history for a project (reference images staging).
    """
    try:
        draft = generation_history_repo.get_draft_by_project(project_id)
        if not draft:
            return jsonify({"history": None}), 200

        return jsonify({
            "history": {
                "id": draft.id,
                "project_id": draft.project_id,
                "user_id": draft.user_id,
                "prompt": draft.prompt,
                "image_ids": draft.image_ids,
                "reference_image_ids": draft.reference_image_ids or [],
                "status": draft.status,
                "prediction_id": draft.prediction_id,
                "provider": draft.provider,
                "error_message": draft.error_message,
                "include_subject_description": draft.include_subject_description,
                "created_at": draft.created_at.isoformat() if draft.created_at else None,
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@generation_history_controller.route('/draft/<string:project_id>/prompt', methods=['PUT'])
def update_draft_prompt(project_id: str):
    """
    Update the prompt for the draft generation history of a project.
    """
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt", "")
        include_subject_description = data.get("include_subject_description")

        draft = generation_history_repo.update_draft_prompt(
            project_id,
            prompt,
            include_subject_description=include_subject_description,
        )
        return jsonify({
            "id": draft.id,
            "project_id": draft.project_id,
            "user_id": draft.user_id,
            "prompt": draft.prompt,
            "image_ids": draft.image_ids,
            "reference_image_ids": draft.reference_image_ids or [],
            "status": draft.status,
            "prediction_id": draft.prediction_id,
            "provider": draft.provider,
            "error_message": draft.error_message,
            "include_subject_description": draft.include_subject_description,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@generation_history_controller.route('/<string:history_id>/status', methods=['GET'])
def update_history_status(history_id: str):
    """
    Update and return the status of a generation history entry
    """
    try:
        history = model_service.update_generation_history_status(history_id)
        return jsonify({
            "id": history.id,
            "project_id": history.project_id,
            "user_id": history.user_id,
            "prompt": history.prompt,
            "image_ids": history.image_ids,
            "reference_image_ids": history.reference_image_ids or [],
            "status": history.status,
            "prediction_id": history.prediction_id,
            "provider": history.provider,
            "error_message": history.error_message,
            "include_subject_description": history.include_subject_description,
            "created_at": history.created_at.isoformat() if history.created_at else None,
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
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
