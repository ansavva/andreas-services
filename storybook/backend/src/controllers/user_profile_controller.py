from flask import Blueprint, request, jsonify

from src.repositories.db.user_profile_repo import UserProfileRepo
from src.repositories.db.image_repo import ImageRepo
from src.services.image_service import ImageService

user_profile_controller = Blueprint("user_profile_controller", __name__)
user_profile_repo = UserProfileRepo()
image_repo = ImageRepo()
image_service = ImageService()

@user_profile_controller.route('/me', methods=['GET'])
def get_my_profile():
    """
    Get the current user's profile (creates one if it doesn't exist)
    """
    try:
        profile = user_profile_repo.get_or_create()

        return jsonify({
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "profile_image_id": profile.profile_image_id,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@user_profile_controller.route('/me', methods=['PUT'])
def update_my_profile():
    """
    Update the current user's profile

    Request body:
        {
            "display_name": "John Doe" (optional)
        }
    """
    try:
        data = request.get_json()
        display_name = data.get("display_name")

        profile = user_profile_repo.update(display_name=display_name)

        return jsonify({
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "profile_image_id": profile.profile_image_id,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@user_profile_controller.route('/me/profile-image', methods=['POST'])
def upload_profile_image():
    """
    Upload a profile image for the current user
    Stores in S3 under users/{user_id}/profile_image.{ext}
    """
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image file provided"}), 400

        file = request.files['image']

        if not file.filename:
            return jsonify({"error": "No file selected"}), 400

        # Get current user ID from Cognito claims
        user_id = request.cognito_claims['sub']

        # Upload the image (will be stored under users/{user_id}/images/...)
        # We use a dummy project_id = user_id for profile images
        image = image_service.upload_image(user_id, file, file.filename)

        # Update user profile with new image ID
        profile = user_profile_repo.update(profile_image_id=image.id)

        return jsonify({
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "profile_image_id": profile.profile_image_id,
            "image": {
                "id": image.id,
                "filename": image.filename,
                "content_type": image.content_type
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@user_profile_controller.route('/<string:user_id>', methods=['GET'])
def get_profile_by_id(user_id: str):
    """
    Get a user profile by user_id (public endpoint for viewing other users)
    """
    try:
        profile = user_profile_repo.get_by_id(user_id)

        if not profile:
            # Return a minimal profile if none exists
            return jsonify({
                "user_id": user_id,
                "display_name": None,
                "profile_image_id": None
            }), 200

        return jsonify({
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "profile_image_id": profile.profile_image_id,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
