# Deployment Instructions for Linux Homeserver

## Prerequisites

1. Python 3.11+ installed
2. `uv` package manager installed
3. Project cloned to your server

## Setup

### 1. Clone and Install Dependencies

```bash
cd /opt  # or wherever you want to install
git clone <your-repo-url> agentic-job-applier
cd agentic-job-applier
uv sync
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual values:
# - APIFY_API_TOKEN (get from https://console.apify.com/account/integrations)
nano .env
```

### 3. Test Manually

```bash
uv run python main.py
```

### 4. Install systemd Service

```bash
# Edit the service file to match your paths and username
sudo nano deploy/job-discovery.service
# Update:
#   User=YOUR_USERNAME
#   WorkingDirectory=/opt/agentic-job-applier
#   Environment="PATH=/opt/agentic-job-applier/.venv/bin"
#   ExecStart=/opt/agentic-job-applier/.venv/bin/python main.py

# Copy files to systemd
sudo cp deploy/job-discovery.service /etc/systemd/system/
sudo cp deploy/job-discovery.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the timer
sudo systemctl enable job-discovery.timer
sudo systemctl start job-discovery.timer
```

### 5. Verify

```bash
# Check timer status
sudo systemctl status job-discovery.timer

# List all timers
systemctl list-timers --all | grep job-discovery

# Run manually to test
sudo systemctl start job-discovery.service

# Check logs
journalctl -u job-discovery.service -f
```

## Useful Commands

```bash
# Stop the timer
sudo systemctl stop job-discovery.timer

# Disable the timer
sudo systemctl disable job-discovery.timer

# Check recent runs
journalctl -u job-discovery.service --since "1 hour ago"

# Check application logs
tail -f /opt/agentic-job-applier/logs/job_monitor.log
```

## Troubleshooting

1. **Permission errors**: Make sure the User in the service file owns the project directory
2. **Python not found**: Verify the path to the .venv/bin/python is correct
3. **Module not found**: Run `uv sync` to install dependencies
4. **Database errors**: Check that data/ directory is writable
