"""Gunicorn settings for Render (``gunicorn -c gunicorn.conf.py app:app``)."""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# I/O-bound work (LLM + HTTP APIs) and long-lived SSE streams: few processes, many threads.
# Each streaming answer holds a thread for its duration, so threads = concurrent chats per worker.
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "8"))
timeout = 180          # a research run can take a while; SSE keep-alives arrive every 15s
graceful_timeout = 30
keepalive = 75

# Import the app (and the heavy LangChain/Gemini modules) once in the master, then fork:
# workers start fast and share memory pages.
preload_app = True

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")


def post_fork(server, worker):
    """Warm per-process clients so the first request after a (re)start is not slower."""
    try:
        from airaa.agent.llm import planner_llm, synthesis_llm

        planner_llm()
        synthesis_llm()
    except Exception as exc:  # missing key etc. must not stop the worker from booting
        server.log.warning("LLM warm-up skipped: %s", exc)
