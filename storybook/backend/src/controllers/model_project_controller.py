from flask import Blueprint, request, jsonify

from src.services.model_project_service import ModelProjectService
from src.models.model_project import ModelProject
from src.config.replicate_config import replicate_config
from src.config.generation_models_config import generation_models_config

model_project_controller = Blueprint("model_project_controller", __name__)
model_project_service = ModelProjectService()

@model_project_controller.route("/model-types", methods=["GET"])
def get_model_types():
    """
    Get all available model types (both training-based and generation-only)

    Returns model types with a 'requires_training' flag to help frontend
    determine workflow (train -> generate vs. direct generate)
    """
    try:
        model_types = []

        # Add training-based models (Replicate training models)
        training_profiles = replicate_config.get_available_profiles()
        for profile in training_profiles:
            model_types.append({
                **profile,
                "requires_training": True,
                "provider": "replicate",
                "type": "training"
            })

        # Add generation-only models (Stability AI + Replicate generation models)
        gen_providers = generation_models_config.get_providers()
        for provider in gen_providers:
            profiles = generation_models_config.get_available_profiles(provider)
            for profile in profiles:
                # Get reference image requirements
                ref_img_reqs = generation_models_config.get_reference_image_requirements(
                    provider,
                    profile['id']
                )

                model_types.append({
                    **profile,
                    "requires_training": False,
                    "provider": provider,
                    "type": "generation",
                    "reference_images": ref_img_reqs or {
                        "required": False,
                        "min": 0,
                        "max": 0,
                        "description": "No reference images supported"
                    }
                })

        # Determine default (prefer training models for now, as that's the existing flow)
        default_model_type = replicate_config.get_default_profile()

        return jsonify({
            "modelTypes": model_types,
            "defaultModelType": default_model_type
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_project_controller.route("", methods=["GET"])
def get_model_projects():
    try:
        # Fetch all model projects
        projects = model_project_service.get_projects()
        # Convert the list of ModelProject objects to dictionaries for JSON response
        project_list = [project.__dict__ for project in projects]
        return jsonify(project_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_project_controller.route("/<string:project_id>", methods=["GET"])
def get_model_project(project_id):
    try:
        # Fetch the model project by ID
        project = model_project_service.get_project(project_id)
        # Return the model project as a dictionary
        return jsonify(project.__dict__), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_project_controller.route("", methods=["POST"])
def create_model_project():
    try:
        # Retrieve project name from request JSON
        data = request.get_json()
        name = data.get("name")
        subject_name = data.get('subjectName')
        subject_description = data.get('subjectDescription')
        model_type = data.get('modelType', ModelProject.DEFAULT_MODEL_TYPE)
        if not name:
            return jsonify({"error": "Project name is required"}), 400
        if not subject_name:
            return jsonify({"error": "Subject name is required"}), 400
        if model_type not in ModelProject.VALID_MODEL_TYPES:
            return jsonify({"error": "Invalid model type"}), 400
        # Create a new model project
        project = model_project_service.create_project(name, subject_name, model_type, subject_description)
        return jsonify(project.__dict__), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_project_controller.route("/<string:project_id>/status", methods=["PUT"])
def update_model_project_status(project_id):
    """Update model project status"""
    try:
        data = request.get_json()
        status = data.get("status")

        if not status:
            return jsonify({"error": "Status is required"}), 400

        project = model_project_service.update_status(project_id, status)
        return jsonify(project.__dict__), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_project_controller.route("/<string:project_id>", methods=["PUT"])
def update_model_project(project_id):
    """Update model project fields"""
    try:
        data = request.get_json()

        project = model_project_service.update_project(
            project_id=project_id,
            name=data.get("name"),
            subject_name=data.get("subjectName"),
            model_type=data.get("modelType"),
            subject_description=data.get("subjectDescription")
        )
        return jsonify(project.__dict__), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@model_project_controller.route("/<string:project_id>", methods=["DELETE"])
def delete_model_project(project_id):
    """Delete a project and all associated data"""
    try:
        model_project_service.delete_project(project_id)
        return jsonify({"message": "Project deleted successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
