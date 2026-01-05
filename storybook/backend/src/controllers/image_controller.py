from flask import Blueprint, request, jsonify, send_file
from io import BytesIO

from src.services.image_service import ImageService
from src.utils.logging.error_logging import log_error

image_controller = Blueprint("image_controller", __name__)
image_service = ImageService()

@image_controller.route("/upload/presign", methods=["POST"])
def presign_image_upload():
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id")
        files = data.get("files", [])
        image_type = data.get("image_type", "training")

        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not files:
            return jsonify({"error": "No files provided"}), 400

        uploads = image_service.create_presigned_uploads(project_id, files, image_type)
        return jsonify({"uploads": uploads}), 200
    except Exception as e:
        log_error(e, "image presign")
        return jsonify({"error": str(e)}), 500

@image_controller.route("/upload/dispatch", methods=["POST"])
def dispatch_image_upload():
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id")
        uploads = data.get("uploads", [])
        image_type = data.get("image_type", "training")

        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if not uploads:
            return jsonify({"error": "No uploads provided"}), 400

        images = image_service.dispatch_presigned_uploads(project_id, uploads, image_type)
        return jsonify({"images": images}), 200
    except Exception as e:
        log_error(e, "image complete upload")
        return jsonify({"error": str(e)}), 500

@image_controller.route("/upload", methods=["POST"])
def upload_image():
    try:
        # Retrieve project_id and image_type from request form data
        project_id = request.form.get("project_id")
        image_type = request.form.get("image_type", "training")  # Default to "training"

        # Validate required data
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        resize_images = request.form.get("resize_images", "true")
        should_resize = str(resize_images).lower() != "false"

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
            # Call the image service to upload the file with the specified image_type
            image = image_service.upload_image(
                project_id,
                file,
                file.filename,
                image_type,
                should_resize,
            )

            # Collect the result for each file upload (convert to dict for JSON)
            uploaded_images.append({
                "id": image.id,
                "filename": image.filename,
                "content_type": image.content_type,
                "size_bytes": image.size_bytes,
                "image_type": image.image_type,
                "processing": image.processing,
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

        # Get image metadata to retrieve filename and storage key
        from src.repositories.db.image_repo import ImageRepo
        repo = ImageRepo()
        image = repo.get_image(image_id)

        presigned_url = repo.storage.generate_presigned_download(image.s3_key)
        return jsonify({"url": presigned_url}), 200
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

        # Get optional image_type filter from query parameters
        image_type = request.args.get("image_type")

        images = image_service.list_images(project_id, image_type)

        # Convert images to dict for JSON response
        images_data = [{
            "id": img.id,
            "filename": img.filename,
            "content_type": img.content_type,
            "size_bytes": img.size_bytes,
            "image_type": img.image_type,
            "processing": img.processing,
            "created_at": img.created_at.isoformat() if img.created_at else None
        } for img in images]

        return jsonify({"images": images_data}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, "image list")
        return jsonify({"error": str(e)}), 500


@image_controller.route("/draft/<project_id>", methods=["GET"])
def list_draft_training_images(project_id):
    try:
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        images = image_service.list_draft_training_images(project_id)
        images_data = [{
            "id": img.id,
            "filename": img.filename,
            "content_type": img.content_type,
            "size_bytes": img.size_bytes,
            "image_type": img.image_type,
            "processing": img.processing,
            "created_at": img.created_at.isoformat() if img.created_at else None
        } for img in images]

        return jsonify({"images": images_data}), 200
    except Exception as e:
        log_error(e, "image draft list")
        return jsonify({"error": str(e)}), 500


@image_controller.route("/status", methods=["GET"])
def image_status():
    try:
        ids_param = request.args.get("ids")
        if not ids_param:
            return jsonify({"error": "ids query parameter is required"}), 400

        image_ids = [item.strip() for item in ids_param.split(",") if item.strip()]
        if not image_ids:
            return jsonify({"error": "ids query parameter is required"}), 400

        images = image_service.get_images_by_ids(image_ids)
        images_data = [{
            "id": img.id,
            "filename": img.filename,
            "content_type": img.content_type,
            "size_bytes": img.size_bytes,
            "image_type": img.image_type,
            "processing": img.processing,
            "created_at": img.created_at.isoformat() if img.created_at else None
        } for img in images]

        return jsonify({"images": images_data}), 200
    except Exception as e:
        log_error(e, "image status")
        return jsonify({"error": str(e)}), 500
