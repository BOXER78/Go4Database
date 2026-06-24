#!/bin/bash

# Navigate to the repository folder
cd /home/go4database.in/public_html/Go4Database

# Discard local modifications to avoid pull conflicts
git reset --hard HEAD
git pull origin main

# Activate the virtualenv and install any new dependencies
/home/go4database.in/backend/venv/bin/pip install -r AI-blog-agent/requirements.txt

# 1. Restart the AI Email Outreach Agent (Port 8080)
pkill -f "uvicorn main:app"
PYTHONUNBUFFERED=1 nohup /home/go4database.in/backend/venv/bin/uvicorn \
main:app \
--host 127.0.0.1 \
--port 8080 \
--app-dir AI-email-automation-agent/backend \
> /home/go4database.in/logs/app.log 2>&1 &

# 2. Restart the AI Blog Writer Agent (Port 8001)
fuser -k 8001/tcp
cd AI-blog-agent
PORT=8001 HOST=127.0.0.1 PYTHONUNBUFFERED=1 nohup /home/go4database.in/backend/venv/bin/python -m backend.main > backend.log 2>&1 &

# 3. Restart LiteSpeed Web Server to refresh everything
systemctl restart lsws

echo "Deployment complete! Email Outreach Agent (8080) and Blog Writer Agent (8001) restarted."
