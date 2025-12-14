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

@model_controller.route("/train", methods=["GET"])
def train():
    try:
        # Retrieve project_id from request args
        project_id = request.args.get("project_id")

        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        training_id = model_service.train(project_id)
        return jsonify({"training_id": training_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_controller.route("/train/status/<string:training_id>", methods=["GET"])
def status(training_id):
    try:
        status = model_service.check_training_status(training_id)
        return jsonify({"status": status}), 200
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