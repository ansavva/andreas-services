from flask import Blueprint, request, jsonify
import json

from src.services.model_service import ModelService

model_controller = Blueprint("model_controller", __name__)
model_service = ModelService()

@model_controller.route('/exists/<string:project_id>', methods=['GET'])
def check_model_exists(project_id: str):
    try:
        model_exists = model_service.exists(project_id)
        return jsonify({"model_found": model_exists}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_controller.route("/train", methods=["POST"])
def train():
    try:
        # Retrieve data from request body
        data = request.get_json()
        project_id = data.get("project_id")
        image_ids = data.get("image_ids", [])

        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not image_ids or len(image_ids) == 0:
            return jsonify({"error": "At least one image ID is required"}), 400

        training_run = model_service.train(project_id, image_ids)

        return jsonify({
            "id": training_run.id,
            "project_id": training_run.project_id,
            "replicate_training_id": training_run.replicate_training_id,
            "image_ids": training_run.image_ids,
            "status": training_run.status,
            "created_at": training_run.created_at.isoformat() if training_run.created_at else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_controller.route("/train/status/<string:training_id>", methods=["GET"])
def status(training_id):
    try:
        status = model_service.check_training_status(training_id)
        return jsonify({"status": status}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_controller.route("/training-runs/<string:project_id>", methods=["GET"])
def get_training_runs(project_id: str):
    """Get all training runs for a project"""
    try:
        training_runs = model_service.get_training_runs(project_id)

        return jsonify({
            "training_runs": [{
                "id": tr.id,
                "project_id": tr.project_id,
                "replicate_training_id": tr.replicate_training_id,
                "image_ids": tr.image_ids,
                "status": tr.status,
                "created_at": tr.created_at.isoformat() if tr.created_at else None,
                "updated_at": tr.updated_at.isoformat() if tr.updated_at else None,
                "completed_at": tr.completed_at.isoformat() if tr.completed_at else None,
                "error_message": tr.error_message
            } for tr in training_runs]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_controller.route("/training-runs/<string:training_run_id>/status", methods=["GET"])
def update_training_run_status(training_run_id: str):
    """Update and return the status of a training run"""
    try:
        training_run = model_service.update_training_run_status(training_run_id)

        return jsonify({
            "id": training_run.id,
            "status": training_run.status,
            "updated_at": training_run.updated_at.isoformat() if training_run.updated_at else None,
            "completed_at": training_run.completed_at.isoformat() if training_run.completed_at else None,
            "error_message": training_run.error_message
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_controller.route("/generate", methods=["POST"])
def generate():
    """
    Generate an image for a project

    Supports both training models and generation-only models.
    For generation-only models, reference images can be provided based on model requirements.
    """
    try:
        data = request.get_json(silent=True)
        if data:
            project_id = data.get("project_id")
            prompt = data.get("prompt")
        else:
            project_id = request.form.get("project_id")
            prompt = request.form.get("prompt")

        include_subject_description = True
        if data and "include_subject_description" in data:
            include_subject_description = bool(data.get("include_subject_description"))
        elif request.form.get("include_subject_description") is not None:
            include_subject_description = request.form.get("include_subject_description", "false").lower() == "true"

        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        # Get reference images if provided directly
        reference_images = []
        if request.files:
            files = request.files.getlist('reference_images')
            reference_images = [f for f in files if f.filename]

        # Get reference image IDs (existing uploads) if provided
        reference_image_ids = None
        reference_ids_source = (
            data.get("reference_image_ids") if data
            else request.form.get("reference_image_ids")
        )
        if reference_ids_source:
            if isinstance(reference_ids_source, list):
                reference_image_ids = [str(item) for item in reference_ids_source if item]
            else:
                try:
                    parsed_ids = json.loads(reference_ids_source)
                    if isinstance(parsed_ids, list):
                        reference_image_ids = [str(item) for item in parsed_ids if item]
                except (json.JSONDecodeError, TypeError):
                    reference_image_ids = [
                        part.strip() for part in str(reference_ids_source).split(",") if part.strip()
                    ]

        image = model_service.generate(
            prompt=prompt,
            project_id=project_id,
            reference_images=reference_images if reference_images else None,
            reference_image_ids=reference_image_ids,
            include_subject_description=include_subject_description
        )

        # Convert Image object to dict for JSON response
        return jsonify({
            "id": image.id,
            "filename": image.filename,
            "content_type": image.content_type,
            "size_bytes": image.size_bytes,
            "created_at": image.created_at.isoformat() if image.created_at else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
