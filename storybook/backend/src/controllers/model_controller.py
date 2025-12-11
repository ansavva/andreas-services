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
        # Retrieve project_id and directory from request args
        project_id = request.args.get("project_id")
        directory = request.args.get("directory")
        
        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not directory:
            return jsonify({"error": "Directory is required"}), 400
        
        training_id = model_service.train(project_id, directory)
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
            return jsonify({"error": "Project ID and file key are required"}), 400
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        
        file = model_service.generate(prompt, project_id)
        return jsonify(file), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500