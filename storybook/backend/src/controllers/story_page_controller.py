from flask import Blueprint, request, jsonify

from src.data.story_page_repo import StoryPageRepo
from src.utils.error_logging import log_error

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
            illustration_prompt=illustration_prompt
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
        from src.proxies.stability_service import StabilityService
        from src.data.character_asset_repo import CharacterAssetRepo
        from src.data.story_project_repo import StoryProjectRepo
        from src.storage.factory import get_file_storage
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
        storage = get_file_storage()
        portrait_data = storage.download_file(portrait.s3_key)

        # Generate illustration
        stability_service = StabilityService()
        image_data = stability_service.generate_story_illustration(
            prompt=page.illustration_prompt,
            character_bible=character_bible.bible_data,
            character_reference=portrait_data
        )

        # Upload to storage
        image_id = str(uuid.uuid4())
        user_id = request.cognito_claims['sub']
        s3_key = f"users/{user_id}/projects/{page.project_id}/pages/{page_id}/illustrations/{image_id}.png"
        storage.upload_file(image_data, s3_key)

        # Update page with image
        page = story_page_repo.update_image(page_id, s3_key)

        return jsonify(page.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@story_page_controller.route("/<string:page_id>", methods=["DELETE"])
def delete_story_page(page_id):
    """Delete a story page"""
    try:
        story_page_repo.delete(page_id)
        return jsonify({"message": "Story page deleted successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@story_page_controller.route("/project/<string:project_id>/export", methods=["GET"])
def export_storybook_pdf(project_id):
    """Export storybook as PDF"""
    try:
        from src.services.pdf_export_service import PDFExportService
        from src.data.story_project_repo import StoryProjectRepo
        from src.storage.factory import get_file_storage
        from flask import send_file

        # Get project
        project_repo = StoryProjectRepo()
        project = project_repo.get_by_id(project_id)

        # Get all pages for the project
        pages = story_page_repo.get_by_project(project_id)

        if not pages:
            return jsonify({"error": "No pages found for this project"}), 400

        # Download all page images
        storage = get_file_storage()
        page_images = {}

        for page in pages:
            if page.image_s3_key:
                try:
                    image_data = storage.download_file(page.image_s3_key)
                    page_images[page._id] = image_data
                except Exception as e:
                    log_error(e, f"download_image_{page._id}")
                    # Continue without this image - placeholder will be used

        # Generate PDF
        pdf_service = PDFExportService()
        pdf_buffer = pdf_service.generate_storybook_pdf(
            story_title=project.story_state.title if project.story_state else "Untitled Story",
            child_name=project.child_name,
            pages=pages,
            page_images=page_images,
            page_size="letter"
        )

        # Update project status to EXPORTED
        project_repo.update_status(project_id, "EXPORTED")

        # Generate filename
        safe_title = "".join(c for c in (project.story_state.title if project.story_state else "story") if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{safe_title}_{project.child_name}.pdf".replace(" ", "_")

        # Return PDF file
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
