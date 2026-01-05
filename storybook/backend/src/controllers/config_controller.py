from flask import Blueprint, jsonify
from src.utils.config.generation_models_config import generation_models_config

config_controller = Blueprint("config_controller", __name__)

@config_controller.route("/style-presets", methods=["GET"])
def get_style_presets():
    """Get list of available style presets for character generation (style transfer)"""
    try:
        # Use style transfer styles (backend-owned reference images)
        # These are the valid style_id values that map to reference images
        provider = "stability_ai"
        profile = "style_transfer"

        presets = list(generation_models_config.get_all_style_references().keys())
        default_style = generation_models_config.get_style_reference_id(provider, profile)

        return jsonify({
            "presets": presets,
            "default": default_style
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
