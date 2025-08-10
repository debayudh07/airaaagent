import os
import asyncio
from typing import Optional
from datetime import datetime

from flask import Flask, request, jsonify, make_response
from flask_cors import CORS

# Import agent components
from main import OptimizedWeb3ResearchAgent, ResearchRequest, init_http_client, http_client


def create_app() -> Flask:
    app = Flask(__name__)

    # Configure CORS explicitly for API routes
    allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
    allowed_origins = (
        "*"
        if allowed_origins_env.strip() == "*"
        else [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    )

    CORS(
        app,
        origins=allowed_origins,
        methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        supports_credentials=False,
        send_wildcard=True,
        vary_header=True,
        max_age=3600,
        always_send=True,
    )

    @app.after_request
    def add_cors_headers(response):
        try:
            # Only apply to API routes
            if request.path.startswith("/api/"):
                request_origin = request.headers.get("Origin")
                # Default to wildcard when allowed_origins is '*'
                if allowed_origins == "*":
                    response.headers["Access-Control-Allow-Origin"] = "*"
                else:
                    if request_origin and isinstance(allowed_origins, list) and request_origin in allowed_origins:
                        response.headers["Access-Control-Allow-Origin"] = request_origin
                # Common headers
                if "Access-Control-Allow-Origin" in response.headers:
                    response.headers["Vary"] = "Origin"
                    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        except Exception:
            pass
        return response

    # Initialize shared HTTP client once for all requests
    try:
        if http_client is None:
            asyncio.run(init_http_client())
    except RuntimeError:
        # Fallback for environments with an existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a dedicated new loop for initialization
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_loop.run_until_complete(init_http_client())
            asyncio.set_event_loop(loop)
        else:
            loop.run_until_complete(init_http_client())

    @app.route("/api/health", methods=["GET"])
    def health() -> tuple:
        return jsonify({"status": "ok"}), 200

    # Explicit preflight handlers to ensure CORS headers on OPTIONS
    @app.route("/api/health", methods=["OPTIONS"])
    def health_preflight():
        return make_response("", 200)

    @app.route("/api/research", methods=["POST"])
    def research_route():
        try:
            payload = request.get_json(force=True) or {}
            query: str = payload.get("query", "")
            address: Optional[str] = payload.get("address")
            time_range: str = payload.get("time_range", "7d")
            session_id: Optional[str] = payload.get("session_id")

            if not query or not isinstance(query, str):
                return jsonify({"success": False, "error": "Field 'query' (string) is required"}), 400

            # Create agent with session support for conversation memory
            agent = OptimizedWeb3ResearchAgent(session_id=session_id)

            async def run_research():
                req = ResearchRequest(query=query, address=address, time_range=time_range, session_id=session_id)
                return await agent.research(req)

            # Execute the coroutine
            try:
                result = asyncio.run(run_research())
            except RuntimeError:
                # If we're already in an event loop (e.g., in some WSGI setups), use a new loop
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(run_research())
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)

            # Add session_id to response for client tracking
            if result.get("success"):
                result["session_id"] = agent.session_id

            return jsonify(result), 200 if result.get("success") else 502
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/research", methods=["OPTIONS"])
    def research_preflight():
        return make_response("", 200)

    @app.route("/api/conversation/<session_id>", methods=["GET"])
    def get_conversation(session_id: str):
        """Get conversation history for a session"""
        try:
            from main import session_manager
            
            if session_id not in session_manager.sessions:
                return jsonify({"success": False, "error": "Session not found"}), 404
            
            session = session_manager.sessions[session_id]
            chat_history = session["chat_history"]
            
            # Convert messages to serializable format
            messages = []
            for msg in chat_history.messages:
                if hasattr(msg, 'content'):
                    messages.append({
                        "type": "human" if msg.__class__.__name__ == "HumanMessage" else "ai",
                        "content": msg.content,
                        "timestamp": session.get("last_activity", datetime.now()).isoformat()
                    })
            
            return jsonify({
                "success": True,
                "session_id": session_id,
                "messages": messages,
                "message_count": len(messages),
                "created_at": session["created_at"].isoformat(),
                "last_activity": session["last_activity"].isoformat()
            })
            
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/conversation/<session_id>", methods=["OPTIONS"])
    def conversation_preflight(session_id: str):
        return make_response("", 200)

    @app.route("/api/sessions", methods=["GET"])
    def list_sessions():
        """List all active sessions"""
        try:
            from main import session_manager
            
            sessions = []
            for session_id, session in session_manager.sessions.items():
                sessions.append({
                    "session_id": session_id,
                    "message_count": session["message_count"],
                    "created_at": session["created_at"].isoformat(),
                    "last_activity": session["last_activity"].isoformat()
                })
            
            return jsonify({
                "success": True,
                "sessions": sessions,
                "total_sessions": len(sessions)
            })
            
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/sessions", methods=["OPTIONS"])
    def sessions_preflight():
        return make_response("", 200)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")

