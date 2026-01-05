from flask import Blueprint, request, jsonify

from src.repositories.db.story_page_repo import StoryPageRepo
from src.utils.logging.error_logging import log_error

story_page_controller = Blueprint("story_page_controller", __name__)
story_page_repo = StoryPageRepo()


@story_page_controller.route("/project/<string:project_id>", methods=["GET"])
def get_story_pages(project_id):
    """Get all pages for a story project"""
    try:
        pages = story_page_repo.get_by_project(project_id)
        pages_list = [page.to_dict() for page in pages]
        return jsonify(pages_list), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_page_controller.route("/<string:page_id>", methods=["GET"])
def get_story_page(page_id):
    """Get a specific story page"""
    try:
        page = story_page_repo.get_by_id(page_id)
        return jsonify(page.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_page_controller.route("", methods=["POST"])
def create_story_page():
    """Create a new story page"""
    try:
        data = request.get_json()
        project_id = data.get("project_id")
        page_number = data.get("page_number")
        page_text = data.get("page_text")
        illustration_prompt = data.get("illustration_prompt")

        # Validation
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400
        if page_number is None:
            return jsonify({"error": "Page number is required"}), 400
        if not page_text:
            return jsonify({"error": "Page text is required"}), 400

        page = story_page_repo.create(
            project_id=project_id,
            page_number=page_number,
            page_text=page_text,
            illustration_prompt=illustration_prompt,
        )
        return jsonify(page.to_dict()), 201
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_page_controller.route("/<string:page_id>/text", methods=["PUT"])
def update_page_text(page_id):
    """Update page text (creates new version)"""
    try:
        data = request.get_json()
        page_text = data.get("page_text")
        if not page_text:
            return jsonify({"error": "Page text is required"}), 400
        page = story_page_repo.update_text(page_id, page_text)
        return jsonify(page.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_page_controller.route("/<string:page_id>/prompt", methods=["PUT"])
def update_illustration_prompt(page_id):
    """Update illustration prompt for a page"""
    try:
        data = request.get_json()
        illustration_prompt = data.get("illustration_prompt")
        if not illustration_prompt:
            return jsonify({"error": "Illustration prompt is required"}), 400
        page = story_page_repo.update_prompt(page_id, illustration_prompt)
        return jsonify(page.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_page_controller.route("/<string:page_id>/generate-image", methods=["POST"])
def generate_page_image(page_id):
    """Generate image for a page using Stability.ai"""
    try:
        from src.services.external.stability_service import StabilityService
        from src.repositories.db.character_asset_repo import CharacterAssetRepo
        from src.repositories.db.story_project_repo import StoryProjectRepo
        from src.services.aws.s3 import S3Storage
        import uuid

        # Get the page
        page = story_page_repo.get_by_id(page_id)

        # Get the project to find character bible
        project_repo = StoryProjectRepo()
        project = project_repo.get_by_id(page.project_id)
        if not project.character_bible_id:
            return jsonify({"error": "Character bible not found for project"}), 400

        # Get character bible
        character_asset_repo = CharacterAssetRepo()
        character_bible = character_asset_repo.get_by_id(project.character_bible_id)

        # Get character portrait for reference
        portrait = character_asset_repo.get_portrait(page.project_id)
        if not portrait or not portrait.s3_key:
            return jsonify({"error": "Character portrait not found"}), 400

        # Download portrait image
        storage = S3Storage()
        portrait_data = storage.download_file(portrait.s3_key)

        # Generate illustration
        stability_service = StabilityService()
        image_data = stability_service.generate_story_illustration(
            prompt=page.illustration_prompt,
            character_bible=character_bible.bible_data,
            character_reference=portrait_data,
        )

        # Upload to storage
        image_id = str(uuid.uuid4())
        user_id = request.cognito_claims["sub"]
        s3_key = (
            f"users/{user_id}/projects/{page.project_id}/pages/{page_id}"
            f"/illustrations/{image_id}.png"
        )
        storage.upload_file(image_data, s3_key)

        # Update page with image
        page = story_page_repo.update_image(page_id, s3_key)
        return jsonify(page.to_dict()), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_page_controller.route("/project/<string:project_id>/export", methods=["GET"])
def export_story_pdf(project_id):
    """Export story as PDF"""
    try:
        from src.services.pdf_export_service import PDFExportService
        from src.repositories.db.story_project_repo import StoryProjectRepo
        from src.services.aws.s3 import S3Storage

        project_repo = StoryProjectRepo()
        project = project_repo.get_by_id(project_id)
        pages = story_page_repo.get_by_project(project_id)

        # Download all page images
        storage = S3Storage()
        page_images = {}
        for page in pages:
            if page.image_s3_key:
                try:
                    image_data = storage.download_file(page.image_s3_key)
                    page_images[page._id] = image_data
                except Exception as e:
                    log_error(e, f"download_image_{page._id}")
                    # Continue without this image - placeholder will be used
                    continue

        # Generate PDF
        pdf_service = PDFExportService()
        pdf_data = pdf_service.create_story_pdf(project, pages, page_images=page_images)

        # Return as file download
        response = jsonify({"status": "ok"})
        response = response.make_response(pdf_data)
        response.headers["Content-Type"] = "application/pdf"
        response.headers[
            "Content-Disposition"
        ] = f"attachment; filename=storybook_{project_id}.pdf"
        return response
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
