from flask import Blueprint, request, jsonify

from src.services.chat.chat_message_service import ChatMessageService
from src.services.chat.story_chat_service import StoryChatService
from src.utils.logging.error_logging import log_error

story_chat_controller = Blueprint("story_chat_controller", __name__)
chat_message_service = ChatMessageService()
story_chat_service = StoryChatService()


@story_chat_controller.route("/story-project/<string:project_id>/chat/messages", methods=["GET"])
def get_story_chat_messages(project_id):
    """Get chat conversation for a story project."""
    try:
        limit = request.args.get("limit", type=int)
        message_list = chat_message_service.get_messages(project_id, limit)
        return jsonify({"messages": message_list}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_chat_controller.route("/story-project/<string:project_id>/chat/messages", methods=["POST"])
def send_story_chat_message(project_id):
    """Send a story chat message and get AI response."""
    try:
        data = request.get_json() or {}
        user_message = data.get("message")
        system_prompt = story_chat_service.build_system_prompt(project_id)
        result = chat_message_service.send_message(
            project_id,
            user_message,
            system_prompt=system_prompt,
        )
        return jsonify(result), 200

    except PermissionError as e:
        if e.args and e.args[0] == "moderation":
            moderation_result = e.args[1]
            return jsonify({
                "error": "Your message contains content that violates our guidelines. Please rephrase and try again.",
                "moderation": moderation_result,
            }), 400
        raise
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_chat_controller.route("/story-project/<string:project_id>/chat/state/generate", methods=["POST"])
def generate_story_state(project_id):
    """Generate structured story state from conversation."""
    try:
        conversation = chat_message_service.get_conversation_for_openai(project_id)
        result = story_chat_service.generate_story_state(project_id, conversation)
        return jsonify(result), 201

    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_chat_controller.route("/story-project/<string:project_id>/chat/state", methods=["GET"])
def get_story_state(project_id):
    """Get current story state for a project."""
    try:
        story_state = story_chat_service.get_story_state(project_id)
        if not story_state:
            return jsonify({"error": "No story state found"}), 404
        return jsonify(story_state), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_chat_controller.route("/story-project/<string:project_id>/chat/state/versions", methods=["GET"])
def get_story_state_versions(project_id):
    """Get all versions of story state."""
    try:
        version_list = story_chat_service.get_story_state_versions(project_id)
        return jsonify({"versions": version_list}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_chat_controller.route("/story-project/<string:project_id>/chat/compile", methods=["POST"])
def compile_story(project_id):
    """Compile story into finalized pages with text and illustration prompts."""
    try:
        conversation = chat_message_service.get_conversation_for_openai(project_id)
        result = story_chat_service.compile_story(project_id, conversation)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@story_chat_controller.route("/story-project/<string:project_id>/chat/messages", methods=["DELETE"])
def clear_story_chat(project_id):
    """Clear chat conversation for a story project."""
    try:
        chat_message_service.clear_messages(project_id)
        return jsonify({"message": "Chat cleared successfully"}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
