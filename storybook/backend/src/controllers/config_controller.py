from flask import Blueprint, jsonify
from src.config.prompts_config import prompts_config

config_controller = Blueprint("config_controller", __name__)

@config_controller.route("/style-presets", methods=["GET"])
def get_style_presets():
    """Get list of available style presets for image generation"""
    try:
        presets = prompts_config.get_available_style_presets()
        default_style = prompts_config.get_character_default_style()

        return jsonify({
            "presets": presets,
            "default": default_style
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
