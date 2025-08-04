import azure.functions as func
import json, logging
from utils.cors import cors_response
from services import conversation_service as conv_svc
from routes.state import CONVERSATIONS

logger = logging.getLogger(__name__)
bp = func.Blueprint()

# ────────────────────────────────────────────────────────────
#  /conversation/{session_id}
# ────────────────────────────────────────────────────────────
@bp.function_name(name="ConversationHandler")
@bp.route(route="conversation/{session_id}",
          methods=["GET", "DELETE", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def conversation_handler(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    session_id = req.route_params.get("session_id")
    if not session_id:
        return cors_response("Missing session ID", 400)

    try:
        if req.method == "GET":
            data = conv_svc.fetch_conversation(session_id)
            if not data:
                return cors_response("Conversation not found", 404)
            return cors_response(json.dumps(data), 200, "application/json")

        if req.method == "DELETE":
            removed = conv_svc.delete_conversation(session_id)
            CONVERSATIONS.pop(session_id, None)
            if not removed:
                return cors_response("Conversation not found", 404)
            return cors_response(f"Conversation {session_id} removed", 200)

        return cors_response("Method not allowed", 405)

    except Exception:
        logger.exception("Failed to process conversation request")
        return cors_response("Server error", 500)


# ────────────────────────────────────────────────────────────
#  /conversations  (list)
# ────────────────────────────────────────────────────────────
@bp.function_name(name="ListConversations")
@bp.route(route="conversations",
          methods=["GET", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def list_conversations(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        limit   = int(req.params.get("limit", 100))
        offset  = int(req.params.get("offset", 0))
        user_id = req.params.get("user_id")

        limit = max(1, min(limit, 200))

        items = conv_svc.list_conversations(user_id=user_id,
                                            limit=limit, offset=offset)
        return cors_response(
            json.dumps({"items": items, "limit": limit, "offset": offset}),
            200,
            "application/json",
        )

    except (ValueError, TypeError):
        return cors_response("Bad query parameters", 400)
    except Exception:
        logger.exception("Failed to list conversations")
        return cors_response("Server error", 500)
