from flask import Blueprint, request, jsonify
from werkzeug.datastructures import FileStorage
import uuid

from src.data.character_asset_repo import CharacterAssetRepo
from src.data.child_profile_repo import ChildProfileRepo
from src.data.image_repo import ImageRepo
from src.services.character_generation_service import CharacterGenerationService
from src.storage.factory import get_file_storage
from src.utils.error_logging import log_error
from src.config.generation_models_config import generation_models_config

character_controller = Blueprint("character_controller", __name__)
character_asset_repo = CharacterAssetRepo()
child_profile_repo = ChildProfileRepo()
image_repo = ImageRepo()
character_generation_service = CharacterGenerationService()

@character_controller.route("/project/<string:project_id>", methods=["GET"])
def get_character_assets(project_id):
    """Get all character assets for a project"""
    try:
        asset_type = request.args.get("type")
        assets = character_asset_repo.get_by_project(project_id, asset_type)
        asset_list = [asset.to_dict() for asset in assets]
        return jsonify(asset_list), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@character_controller.route("/project/<string:project_id>/portrait", methods=["POST"])
def generate_character_portrait(project_id):
    """Generate a character portrait from uploaded photos"""
    try:
        # Get child profile
        profile = child_profile_repo.get_by_project_id(project_id)
        if not profile:
            return jsonify({"error": "Child profile not found. Please complete kid setup first."}), 404

        # Get reference images from profile
        if not profile.photo_ids or len(profile.photo_ids) == 0:
            return jsonify({"error": "No photos found. Please upload photos first."}), 400

        # Download reference images from S3
        storage = get_file_storage()
        reference_images = []
        for photo_id in profile.photo_ids:
            image_metadata = image_repo.get_image(photo_id)
            image_data = storage.download_file(image_metadata.s3_key)
            reference_images.append(image_data)

        # Get request body for user_description and style
        data = request.get_json() or {}
        user_description = data.get("user_description")  # Optional custom prompt text
        style = data.get("style")  # Optional style preset (validates in service)

        # Generate portrait with Stability.ai
        result = stability_service.generate_character_portrait(
            reference_images=reference_images,
            child_name=profile.child_name,
            user_description=user_description,
            style=style
        )

        # Convert base64 to bytes and upload using image_repo (same as uploaded photos)
        image_stream = stability_service.image_to_bytes(result["image_data"])
        image_stream.seek(0)

        # Wrap in FileStorage for image_repo
        file_obj = FileStorage(
            stream=image_stream,
            filename="portrait.png",
            content_type="image/png"
        )

        # Upload using image_repo - stores in project_id/{image_id}.png
        image_record = image_repo.upload_image(project_id, file_obj, "portrait.png")

        # Save character asset with reference to image ID
        asset = character_asset_repo.create_image_asset(
            project_id=project_id,
            asset_type="portrait",
            image_id=image_record.id,  # Just store the image ID
            prompt=f"Portrait of {profile.child_name}",
            stability_image_id=str(result.get("seed")),
            version=1
        )

        return jsonify(asset.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@character_controller.route("/project/<string:project_id>/portrait-stylized", methods=["POST"])
def generate_stylized_portrait(project_id):
    """
    Generate a stylized character portrait using Stability AI's style transfer

    This is the RECOMMENDED method for character generation as it better preserves
    kid likeness while applying artistic styles.

    Request body (JSON):
        - user_description: Optional custom description to append to prompt
        - style_id: Optional style identifier (default: "animated_3d")
        - style_strength: Optional 0.0-1.0 (default: from config, typically 0.8)

    Returns:
        Character asset with generated portrait
    """
    try:
        # Get child profile
        profile = child_profile_repo.get_by_project_id(project_id)
        if not profile:
            return jsonify({"error": "Child profile not found. Please complete kid setup first."}), 404

        # Get reference images from profile (kid photos)
        if not profile.photo_ids or len(profile.photo_ids) == 0:
            return jsonify({"error": "No photos found. Please upload photos first."}), 400

        # Get request parameters
        data = request.get_json() or {}
        user_description = data.get("user_description")

        provider = "stability_ai"
        profile_name = "style_transfer"
        gen_config = generation_models_config.get_generation_config(provider, profile_name)

        style_id = data.get("style_id", generation_models_config.get_style_reference_id(provider, profile_name))
        style_strength = data.get("style_strength", gen_config.get("style_strength", 0.7))

        # Validate style_id
        available_styles = list(generation_models_config.get_all_style_references().keys())
        if style_id not in available_styles:
            return jsonify({
                "error": f"Invalid style_id '{style_id}'. Available styles: {available_styles}"
            }), 400

        # Validate style_strength
        if not (0.0 <= style_strength <= 1.0):
            return jsonify({"error": "style_strength must be between 0.0 and 1.0"}), 400

        # Download kid reference image (use first photo as init_image)
        storage = get_file_storage()
        kid_image_metadata = image_repo.get_image(profile.photo_ids[0])
        init_image = storage.download_file(kid_image_metadata.s3_key)

        # Call character generation service (handles all the business logic)
        result_bytes = character_generation_service.generate_stylized_portrait(
            init_image=init_image,
            style_id=style_id,
            user_description=user_description,
            style_strength=style_strength,
            profile=profile_name
        )

        # Upload result using image_repo
        from io import BytesIO
        image_stream = BytesIO(result_bytes)

        file_obj = FileStorage(
            stream=image_stream,
            filename="portrait_stylized.png",
            content_type="image/png"
        )

        image_record = image_repo.upload_image(project_id, file_obj, "portrait_stylized.png")

        # Save character asset
        full_prompt = f"{prompt} (style: {style_id}, strength: {style_strength})"
        if user_description:
            full_prompt += f" - {user_description}"

        asset = character_asset_repo.create_image_asset(
            project_id=project_id,
            asset_type="portrait",
            image_id=image_record.id,
            prompt=full_prompt,
            stability_image_id=f"style_transfer_{style_id}",
            version=1
        )

        return jsonify(asset.to_dict()), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@character_controller.route("/asset/<string:asset_id>/approve", methods=["POST"])
def approve_character_asset(asset_id):
    """Approve a character asset (portrait or scene)"""
    try:
        asset = character_asset_repo.approve_asset(asset_id)
        return jsonify(asset.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@character_controller.route("/asset/<string:asset_id>/regenerate", methods=["POST"])
def regenerate_character_asset(asset_id):
    """Regenerate a character asset"""
    try:
        # Get existing asset
        asset = character_asset_repo.get_by_id(asset_id)

        # Get profile
        profile = child_profile_repo.get_by_project_id(asset.project_id)
        if not profile:
            return jsonify({"error": "Child profile not found"}), 404

        # Get storage adapter
        storage = get_file_storage()

        # Get reference images
        reference_images = []
        if profile.photo_ids:
            for photo_id in profile.photo_ids:
                image_metadata = image_repo.get_image(photo_id)
                image_data = storage.download_file(image_metadata.s3_key)
                reference_images.append(image_data)

        # Get request body for optional parameters
        data = request.get_json() or {}
        user_description = data.get("user_description")
        style_id = data.get("style_id")
        style_strength = data.get("style_strength")

        # Regenerate based on asset type
        if asset.asset_type == "portrait":
            # Use style transfer for portrait regeneration
            if not reference_images:
                return jsonify({"error": "No reference images available"}), 400

            provider = "stability_ai"
            profile_name = "style_transfer"
            gen_config = generation_models_config.get_generation_config(provider, profile_name)

            # Load style reference image
            if not style_id:
                style_id = generation_models_config.get_style_reference_id(provider, profile_name)

            if not style_strength:
                style_strength = gen_config.get("style_strength", 0.7)

            # Call character generation service (handles all the business logic)
            result_bytes = character_generation_service.generate_stylized_portrait(
                init_image=reference_images[0],
                style_id=style_id,
                user_description=user_description,
                style_strength=style_strength,
                profile=profile_name
            )

            # Convert bytes to file-like object for compatibility with existing code
            from io import BytesIO
            image_stream = BytesIO(result_bytes)
            result = {"image_data": None}  # Placeholder for compatibility
        else:
            return jsonify({"error": "Cannot regenerate this asset type"}), 400

        # Upload new version using image_repo
        # Handle both new style transfer (bytes) and legacy (base64) formats
        if asset.asset_type == "portrait":
            # image_stream already created above for style transfer
            pass
        else:
            # Legacy format: convert base64 to bytes
            image_stream = stability_service.image_to_bytes(result["image_data"])

        image_stream.seek(0)

        # Wrap in FileStorage for image_repo
        filename = f"{asset.asset_type}.png" if not asset.scene_name else f"scene_{asset.scene_name}.png"
        file_obj = FileStorage(
            stream=image_stream,
            filename=filename,
            content_type="image/png"
        )

        image_record = image_repo.upload_image(asset.project_id, file_obj, filename)

        # Create new asset version with reference to image ID
        new_asset = character_asset_repo.create_image_asset(
            project_id=asset.project_id,
            asset_type=asset.asset_type,
            image_id=image_record.id,
            prompt=asset.prompt,
            scene_name=asset.scene_name,
            stability_image_id=str(result.get("seed")),
            version=asset.version + 1
        )

        return jsonify(new_asset.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@character_controller.route("/project/<string:project_id>/bible", methods=["POST"])
def create_character_bible(project_id):
    """Create or update character bible"""
    try:
        data = request.get_json()
        bible_data = data.get("bible_data")

        if not bible_data:
            return jsonify({"error": "Bible data is required"}), 400

        asset = character_asset_repo.create_character_bible(
            project_id=project_id,
            bible_data=bible_data
        )
        return jsonify(asset.to_dict()), 201
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@character_controller.route("/project/<string:project_id>/bible", methods=["GET"])
def get_character_bible(project_id):
    """Get character bible for a project"""
    try:
        bible = character_asset_repo.get_character_bible(project_id)
        if not bible:
            return jsonify({"error": "Character bible not found"}), 404
        return jsonify(bible.to_dict()), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
