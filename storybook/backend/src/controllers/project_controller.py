from flask import Blueprint, request, jsonify

from src.services.project_service import ProjectService

project_controller = Blueprint("project_controller", __name__)
project_service = ProjectService()

@project_controller.route("", methods=["GET"])
def get_projects():
    try:
        # Fetch all projects
        projects = project_service.get_projects()
        # Convert the list of Project objects to dictionaries for JSON response
        project_list = [project.__dict__ for project in projects]
        return jsonify(project_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@project_controller.route("/<string:project_id>", methods=["GET"])
def get_project(project_id):
    try:
        # Fetch the project by ID
        project = project_service.get_project(project_id)
        # Return the project as a dictionary
        return jsonify(project.__dict__), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@project_controller.route("", methods=["POST"])
def create_project():
    try:
        # Retrieve project name from request JSON
        data = request.get_json()
        name = data.get("name")
        subject_name = data.get('subjectName')
        if not name:
            return jsonify({"error": "Project name is required"}), 400
        if not subject_name:
            return jsonify({"error": "Subject name is required"}), 400
        # Create a new project
        project = project_service.create_project(name, subject_name)
        return jsonify(project.__dict__), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500