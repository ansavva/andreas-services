from flask import Blueprint, request, jsonify, send_file
from io import BytesIO

from src.services.image_service import ImageService
from src.utils.error_logging import log_error

image_controller = Blueprint("image_controller", __name__)
image_service = ImageService()

@image_controller.route("/upload", methods=["POST"])
def upload_image():
    try:
        # Retrieve project_id from request form data
        project_id = request.form.get("project_id")

        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        uploaded_files = []
        for key in request.files:
            if key.startswith('image['):
                uploaded_files.append(request.files[key])

        # If no files were uploaded, return an error
        if not uploaded_files:
            return jsonify({"error": "No files provided"}), 400

        # Initialize response data
        uploaded_images = []

        # Loop through the uploaded files and upload each one
        for file in uploaded_files:
            # Call the image service to upload the file
            image = image_service.upload_image(project_id, file, file.filename)

            # Collect the result for each file upload (convert to dict for JSON)
            uploaded_images.append({
                "id": image.id,
                "filename": image.filename,
                "content_type": image.content_type,
                "size_bytes": image.size_bytes,
                "created_at": image.created_at.isoformat() if image.created_at else None
            })

        return jsonify({"images": uploaded_images}), 200
    except Exception as e:
        log_error(e, "image upload")
        return jsonify({"error": str(e)}), 500

@image_controller.route("/download/<image_id>", methods=["GET"])
def download_image(image_id):
    try:
        # Validate required data
        if not image_id:
            return jsonify({"error": "Image ID is required"}), 400

        file_data = image_service.download_image(image_id)

        if file_data:
            # Get image metadata to retrieve filename
            from src.data.image_repo import ImageRepo
            repo = ImageRepo()
            image = repo.get_image(image_id)
            return send_file(BytesIO(file_data), download_name=image.filename, as_attachment=True)
        return jsonify({"error": "File not found"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, "image download")
        return jsonify({"error": str(e)}), 500

@image_controller.route("/delete/<image_id>", methods=["DELETE"])
def delete_image(image_id):
    try:
        # Validate required data
        if not image_id:
            return jsonify({"error": "Image ID is required"}), 400

        image_service.delete_image(image_id)
        return jsonify({"message": "Image deleted successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, "image delete")
        return jsonify({"error": str(e)}), 500

@image_controller.route("/list/<project_id>", methods=["GET"])
def list_images(project_id):
    try:
        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        images = image_service.list_images(project_id)

        # Convert images to dict for JSON response
        images_data = [{
            "id": img.id,
            "filename": img.filename,
            "content_type": img.content_type,
            "size_bytes": img.size_bytes,
            "created_at": img.created_at.isoformat() if img.created_at else None
        } for img in images]

        return jsonify({"images": images_data}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, "image list")
        return jsonify({"error": str(e)}), 500
