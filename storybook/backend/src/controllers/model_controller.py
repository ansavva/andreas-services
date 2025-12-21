from flask import Blueprint, request, jsonify

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

@model_controller.route("/generate", methods=["GET"])
def generate():
    try:
        project_id = request.args.get("project_id")
        prompt = request.args.get("prompt")

        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        image = model_service.generate(prompt, project_id)

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