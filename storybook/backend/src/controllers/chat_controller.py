from flask import Blueprint, request, jsonify

from src.data.chat_message_repo import ChatMessageRepo
from src.data.story_state_repo import StoryStateRepo
from src.data.story_project_repo import StoryProjectRepo
from src.data.child_profile_repo import ChildProfileRepo
from src.services.openai_service import OpenAIService
from src.utils.error_logging import log_error

chat_controller = Blueprint("chat_controller", __name__)
chat_message_repo = ChatMessageRepo()
story_state_repo = StoryStateRepo()
story_project_repo = StoryProjectRepo()
child_profile_repo = ChildProfileRepo()
openai_service = OpenAIService()

@chat_controller.route("/project/<string:project_id>/messages", methods=["GET"])
def get_chat_messages(project_id):
    """Get chat conversation for a project"""
    try:
        limit = request.args.get("limit", type=int)
        messages = chat_message_repo.get_conversation(project_id, limit)
        message_list = [msg.to_dict() for msg in messages]
        return jsonify({"messages": message_list}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@chat_controller.route("/project/<string:project_id>/messages", methods=["POST"])
def send_chat_message(project_id):
    """Send a user message and get AI response"""
    try:
        data = request.get_json()
        user_message = data.get("message")

        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        # Get child profile for context
        profile = child_profile_repo.get_by_project_id(project_id)
        if not profile:
            return jsonify({"error": "Child profile not found. Please complete kid setup first."}), 404

        # Moderate user input
        moderation_result = openai_service.moderate_content(user_message)
        if moderation_result["flagged"]:
            return jsonify({
                "error": "Your message contains content that violates our guidelines. Please rephrase and try again.",
                "moderation": moderation_result
            }), 400

        # Save user message
        chat_message_repo.add_user_message(project_id, user_message)

        # Get conversation history
        conversation = chat_message_repo.get_conversation_for_openai(project_id)

        # Add system context on first message
        if len(conversation) == 1:
            system_message = f"""You are a creative children's story writer helping to develop a personalized story for {profile.child_name}, age {profile.child_age}.

Your role is to:
1. Collaborate with the user to brainstorm story ideas
2. Ask questions to understand what kind of story they want
3. Develop characters, setting, and plot
4. Keep the story age-appropriate and engaging for a {profile.child_age}-year-old
5. Make {profile.child_name} the main character

Be creative, friendly, and helpful. Guide the user through the story development process."""

            chat_message_repo.add_system_message(project_id, system_message)
            conversation = chat_message_repo.get_conversation_for_openai(project_id)

        # Get AI response
        ai_response = openai_service.chat_completion(
            messages=conversation,
            temperature=0.8
        )

        # Moderate AI response
        response_moderation = openai_service.moderate_content(ai_response["content"])
        if response_moderation["flagged"]:
            # Retry with lower temperature if flagged
            ai_response = openai_service.chat_completion(
                messages=conversation,
                temperature=0.5
            )

        # Save assistant message
        chat_message_repo.add_assistant_message(
            project_id=project_id,
            content=ai_response["content"],
            model=ai_response["model"],
            tokens_used=ai_response["tokens_used"]
        )

        return jsonify({
            "message": ai_response["content"],
            "model": ai_response["model"],
            "tokens_used": ai_response["tokens_used"]
        }), 200

    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@chat_controller.route("/project/<string:project_id>/generate-state", methods=["POST"])
def generate_story_state(project_id):
    """Generate structured story state from conversation"""
    try:
        # Get child profile
        profile = child_profile_repo.get_by_project_id(project_id)
        if not profile:
            return jsonify({"error": "Child profile not found"}), 404

        # Get conversation history
        conversation = chat_message_repo.get_conversation_for_openai(project_id)

        if len(conversation) < 2:
            return jsonify({"error": "Not enough conversation to generate story state"}), 400

        # Generate story state
        result = openai_service.generate_story_state(
            conversation_history=conversation,
            child_name=profile.child_name,
            child_age=profile.child_age
        )

        if not result["structured_data"]:
            return jsonify({"error": "Failed to generate structured story state"}), 500

        story_data = result["structured_data"]

        # Save story state
        story_state = story_state_repo.create_or_update(
            project_id=project_id,
            title=story_data.get("title"),
            age_range=story_data.get("age_range"),
            characters=story_data.get("characters"),
            setting=story_data.get("setting"),
            outline=story_data.get("outline"),
            page_count=story_data.get("page_count"),
            themes=story_data.get("themes"),
            tone=story_data.get("tone")
        )

        # Update project with story state reference
        story_project_repo.update_project(
            project_id=project_id,
            story_state_id=story_state.id
        )

        return jsonify({
            "story_state": story_state.to_dict(),
            "tokens_used": result["tokens_used"]
        }), 201

    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@chat_controller.route("/project/<string:project_id>/state", methods=["GET"])
def get_story_state(project_id):
    """Get current story state for a project"""
    try:
        story_state = story_state_repo.get_current(project_id)
        if not story_state:
            return jsonify({"error": "No story state found"}), 404
        return jsonify(story_state.to_dict()), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@chat_controller.route("/project/<string:project_id>/state/versions", methods=["GET"])
def get_story_state_versions(project_id):
    """Get all versions of story state"""
    try:
        versions = story_state_repo.get_all_versions(project_id)
        version_list = [v.to_dict() for v in versions]
        return jsonify({"versions": version_list}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@chat_controller.route("/project/<string:project_id>/compile", methods=["POST"])
def compile_story(project_id):
    """Compile story into finalized pages with text and illustration prompts"""
    try:
        from src.data.story_page_repo import StoryPageRepo
        from src.data.story_project_repo import StoryProjectRepo

        story_page_repo = StoryPageRepo()
        story_project_repo = StoryProjectRepo()

        # Get current story state
        story_state = story_state_repo.get_current(project_id)
        if not story_state:
            return jsonify({"error": "Story state must be generated first"}), 400

        if not story_state.page_count or story_state.page_count == 0:
            return jsonify({"error": "Story state must have page count"}), 400

        # Get conversation history for context
        conversation = chat_message_repo.get_conversation_for_openai(project_id)

        # Ask OpenAI to generate page content
        compile_prompt = f"""Based on our conversation, please generate the final story with exactly {story_state.page_count} pages.

For each page, provide:
1. Page number
2. Text content (1-3 sentences appropriate for a {story_state.age_range} child)
3. Illustration description (detailed visual description for image generation)

Format your response as JSON:
{{
  "pages": [
    {{
      "page_number": 1,
      "text": "...",
      "illustration_description": "..."
    }},
    ...
  ]
}}

Story details:
- Title: {story_state.title}
- Characters: {', '.join([c.get('name', '') for c in (story_state.characters or [])])}
- Setting: {story_state.setting}
- Outline: {', '.join(story_state.outline or [])}"""

        # Add compile prompt to conversation
        compile_messages = conversation + [{"role": "user", "content": compile_prompt}]

        # Get structured response
        response = openai_service.chat_completion(
            messages=compile_messages,
            temperature=0.7
        )

        # Parse pages from response
        import json
        try:
            pages_data = json.loads(response["content"])
            pages_list = pages_data.get("pages", [])
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response["content"])
            if json_match:
                pages_data = json.loads(json_match.group())
                pages_list = pages_data.get("pages", [])
            else:
                return jsonify({"error": "Failed to parse story pages from AI response"}), 500

        # Delete existing pages
        story_page_repo.delete_by_project(project_id)

        # Create pages
        created_pages = []
        for page_data in pages_list:
            page = story_page_repo.create(
                project_id=project_id,
                page_number=page_data.get("page_number"),
                page_text=page_data.get("text"),
                illustration_prompt=page_data.get("illustration_description")
            )
            created_pages.append(page.to_dict())

        # Update project status to ILLUSTRATING
        story_project_repo.update_status(project_id, "ILLUSTRATING")

        return jsonify({
            "message": "Story compiled successfully",
            "pages": created_pages
        }), 200

    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500

@chat_controller.route("/project/<string:project_id>/messages", methods=["DELETE"])
def clear_chat(project_id):
    """Clear chat conversation for a project"""
    try:
        chat_message_repo.clear_conversation(project_id)
        return jsonify({"message": "Chat cleared successfully"}), 200
    except Exception as e:
        log_error(e, request.endpoint)
        return jsonify({"error": str(e)}), 500
