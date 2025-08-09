import os
import asyncio
from typing import Optional

from flask import Flask, request, jsonify
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
        resources={r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }},
    )

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

    @app.route("/api/research", methods=["POST"])
    def research_route():
        try:
            payload = request.get_json(force=True) or {}
            query: str = payload.get("query", "")
            address: Optional[str] = payload.get("address")
            time_range: str = payload.get("time_range", "7d")

            if not query or not isinstance(query, str):
                return jsonify({"success": False, "error": "Field 'query' (string) is required"}), 400

            # Create a fresh agent per request to avoid shared chat history across users
            agent = OptimizedWeb3ResearchAgent()

            async def run_research():
                req = ResearchRequest(query=query, address=address, time_range=time_range)
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

            return jsonify(result), 200 if result.get("success") else 502

        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")

