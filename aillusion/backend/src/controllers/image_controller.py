from flask import Blueprint, request, jsonify, send_file
from io import BytesIO

from src.services.image_service import ImageService

image_controller = Blueprint("image_controller", __name__)
image_service = ImageService()

@image_controller.route("/upload", methods=["POST"])
def upload_image():
    try:
        # Retrieve project_id and directory from request form data
        project_id = request.form.get("project_id")
        directory = request.form.get("directory")
        
        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not directory:
            return jsonify({"error": "Directoy is required"}), 400
        
        uploaded_files = []
        for key in request.files:
            if key.startswith('image['):
                uploaded_files.append(request.files[key])
        
        # If no files were uploaded, return an error
        if not uploaded_files:
            return jsonify({"error": "No files provided"}), 400
        
        # Initialize response data
        upload_files = []

        # Loop through the uploaded files and upload each one
        for file in uploaded_files:
            # Call the image service to upload the file
            file = image_service.upload_file(project_id, directory, file, file.filename)
            
            # Collect the result for each file upload
            upload_files.append(file)

        return jsonify({"files": upload_files}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@image_controller.route("/download", methods=["GET"])
def download_image():
    try:
        # Retrieve project_id, directory, and key from request args
        project_id = request.args.get("project_id")
        directory = request.args.get("directory")
        key = request.args.get("key")
        
        # Validate required data
        if not project_id or not key:
            return jsonify({"error": "Project ID and file key are required"}), 400
        if not directory:
            return jsonify({"error": "Directoy is required"}), 400
        
        file_data = image_service.download_file(project_id, directory, key)
        
        if file_data:
            return send_file(BytesIO(file_data), download_name=key, as_attachment=True)
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@image_controller.route("/delete", methods=["DELETE"])
def delete_image():
    try:
        # Retrieve project_id, directory, and key from request args
        project_id = request.args.get("project_id")
        directory = request.args.get("directory")
        key = request.args.get("key")
        
        # Validate required data
        if not project_id or not key:
            return jsonify({"error": "Project ID and file key are required"}), 400
        if not directory:
            return jsonify({"error": "Directoy is required"}), 400
        
        image_service.delete_file(project_id, directory, key)
        return jsonify({}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@image_controller.route("/list", methods=["GET"])
def list_images():
    try:
        # Retrieve project_id and directory from request args
        project_id = request.args.get("project_id")
        directory = request.args.get("directory")
        
        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not directory:
            return jsonify({"error": "Directoy is required"}), 400
        
        files = image_service.list_files(project_id, directory)
        return jsonify({"files": files}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
