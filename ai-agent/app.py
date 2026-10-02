"""WSGI entry point: ``gunicorn app:app``. All logic lives in the ``airaa`` package."""
import logging
import os

from airaa.api import create_app

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
