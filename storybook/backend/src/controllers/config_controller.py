from flask import Blueprint, jsonify
from src.config.prompts_config import prompts_config
from src.config.style_references import style_references

config_controller = Blueprint("config_controller", __name__)

@config_controller.route("/style-presets", methods=["GET"])
def get_style_presets():
    """Get list of available style presets for character generation (style transfer)"""
    try:
        # Use style transfer styles (backend-owned reference images)
        # These are the valid style_id values that map to reference images
        presets = style_references.get_available_styles()
        default_style = style_references.get_default_style()

        return jsonify({
            "presets": presets,
            "default": default_style
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
