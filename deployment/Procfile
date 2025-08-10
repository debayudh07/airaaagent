web: sh -c 'if [ -d ai-agent ]; then cd ai-agent; fi; exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 180'

