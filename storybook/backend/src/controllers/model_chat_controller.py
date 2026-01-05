from flask import Blueprint, request, jsonify

from src.services.chat.chat_message_service import ChatMessageService
from src.services.chat.model_chat_service import ModelChatService
from src.utils.logging.error_logging import log_error

model_chat_controller = Blueprint("model_chat_controller", __name__)
chat_message_service = ChatMessageService()
model_chat_service = ModelChatService()


@model_chat_controller.route("/model-project/<string:project_id>/chat/messages", methods=["GET"])
def get_model_chat_messages(project_id):
    """Get chat conversation for a model project."""
    try:
        limit = request.args.get("limit", type=int)
        message_list = chat_message_service.get_messages(project_id, limit)
        return jsonify({"messages": message_list}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500


@model_chat_controller.route("/model-project/<string:project_id>/chat/messages", methods=["POST"])
def send_model_chat_message(project_id):
    """Send a model chat message and get AI response."""
    try:
        data = request.get_json() or {}
        user_message = data.get("message")
        system_prompt = model_chat_service.build_system_prompt(project_id)
        result = chat_message_service.send_message(
            project_id,
            user_message,
            system_prompt=system_prompt,
            temperature=0.7,
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


@model_chat_controller.route("/model-project/<string:project_id>/chat/messages", methods=["DELETE"])
def clear_model_chat(project_id):
    """Clear chat conversation for a model project."""
    try:
        chat_message_service.clear_messages(project_id)
        return jsonify({"message": "Chat cleared successfully"}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
