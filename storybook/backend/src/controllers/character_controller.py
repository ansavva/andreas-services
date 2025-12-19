from flask import Blueprint, request, jsonify
from werkzeug.datastructures import FileStorage
import uuid

from src.data.character_asset_repo import CharacterAssetRepo
from src.data.child_profile_repo import ChildProfileRepo
from src.data.image_repo import ImageRepo
from src.services.stability_service import StabilityService
from src.storage.factory import get_file_storage
from src.utils.error_logging import log_error

character_controller = Blueprint("character_controller", __name__)
character_asset_repo = CharacterAssetRepo()
child_profile_repo = ChildProfileRepo()
image_repo = ImageRepo()
stability_service = StabilityService()

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

@character_controller.route("/project/<string:project_id>/preview-scenes", methods=["POST"])
def generate_preview_scenes(project_id):
    """Generate preview scenes for character"""
    try:
        data = request.get_json()
        scenes = data.get("scenes", ["park", "space", "pirate"])
        style = data.get("style")  # Optional style preset

        # Get child profile
        profile = child_profile_repo.get_by_project_id(project_id)
        if not profile:
            return jsonify({"error": "Child profile not found"}), 404

        # Get approved portrait as reference
        storage = get_file_storage()
        approved_portrait = character_asset_repo.get_approved_portrait(project_id)
        reference_image = None
        if approved_portrait and approved_portrait.image_id:
            image_metadata = image_repo.get_image(approved_portrait.image_id)
            reference_image = storage.download_file(image_metadata.s3_key)

        # Get character description
        character_desc = f"A child named {profile.child_name}, age {profile.child_age}"

        # Generate scenes
        generated_scenes = []
        user_id = request.cognito_claims['sub']

        for scene_name in scenes:
            result = stability_service.generate_preview_scene(
                scene_name=scene_name,
                character_description=character_desc,
                reference_image=reference_image,
                style=style
            )

            # Upload using image_repo - stores in project_id/{image_id}.png
            image_stream = stability_service.image_to_bytes(result["image_data"])
            image_stream.seek(0)

            # Wrap in FileStorage for image_repo
            file_obj = FileStorage(
                stream=image_stream,
                filename=f"scene_{scene_name}.png",
                content_type="image/png"
            )

            image_record = image_repo.upload_image(project_id, file_obj, f"scene_{scene_name}.png")

            # Save asset with reference to image ID
            asset = character_asset_repo.create_image_asset(
                project_id=project_id,
                asset_type="preview_scene",
                image_id=image_record.id,
                prompt=f"{character_desc} in {scene_name}",
                scene_name=scene_name,
                stability_image_id=str(result.get("seed")),
                version=1
            )
            generated_scenes.append(asset.to_dict())

        return jsonify({"scenes": generated_scenes}), 201
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
        style = data.get("style")

        # Regenerate based on asset type
        if asset.asset_type == "portrait":
            result = stability_service.generate_character_portrait(
                reference_images=reference_images,
                child_name=profile.child_name,
                user_description=user_description,
                style=style
            )
        elif asset.asset_type == "preview_scene":
            approved_portrait = character_asset_repo.get_approved_portrait(asset.project_id)
            ref_image = None
            if approved_portrait and approved_portrait.image_id:
                image_metadata = image_repo.get_image(approved_portrait.image_id)
                ref_image = storage.download_file(image_metadata.s3_key)

            result = stability_service.generate_preview_scene(
                scene_name=asset.scene_name,
                character_description=f"A child named {profile.child_name}",
                reference_image=ref_image,
                style=style
            )
        else:
            return jsonify({"error": "Cannot regenerate this asset type"}), 400

        # Upload new version using image_repo
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
