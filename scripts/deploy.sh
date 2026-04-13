#!/bin/bash
# deploy.sh — Sync local code to EC2 and restart the buyer service
# Usage: ./deploy.sh
# Requirements: hederakeypair.pem in project root, EC2_HOST set below

set -e

# ── CONFIG ──────────────────────────────────────────────────────────────────
EC2_HOST="ubuntu@54.90.137.127"       # Update if your EC2 IP changes
PEM="hederakeypair.pem"
REMOTE_DIR="~/hyperplane"
SERVICE_NAME="mlat-buyer"
# ────────────────────────────────────────────────────────────────────────────

echo "=== Step 1: Syncing project files to EC2 (respecting .gitignore) ==="

# Build a single exclude string from .gitignore
# This reads .gitignore, strips comments and blank lines, and passes each
# pattern as --exclude to tar. node_modules, .env files, etc. all excluded.
EXCLUDES="--exclude='.git'"
if [ -f ".gitignore" ]; then
  while IFS= read -r line; do
    # Skip blank lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue
    EXCLUDES="$EXCLUDES --exclude='$line'"
  done < ".gitignore"
fi

# Always exclude sensitive files regardless of .gitignore
EXCLUDES="$EXCLUDES --exclude='.buyer-env' --exclude='hederakeypair.pem' --exclude='*.pem'"

echo "Uploading code (secrets excluded)..."
eval tar -czf - $EXCLUDES . | ssh -i "$PEM" "$EC2_HOST" \
  "mkdir -p $REMOTE_DIR && cd $REMOTE_DIR && tar -xzf -"

# Upload secrets separately with strict permissions
echo "Uploading secrets..."
scp -i "$PEM" .buyer-env "$EC2_HOST:$REMOTE_DIR/.buyer-env"
scp -i "$PEM" location-override.json "$EC2_HOST:$REMOTE_DIR/location-override.json"

echo ""
echo "=== Step 2: Build and install systemd service on EC2 ==="

ssh -i "$PEM" "$EC2_HOST" << 'REMOTE'
  set -e
  cd ~/hyperplane

  # Ensure Go is available
  export PATH=$PATH:/usr/local/go/bin

  # Build the binary
  echo "Building Go binary..."
  go build -o main_app .
  echo "Build successful."

  # Create systemd service file
  # This runs as the ubuntu user, auto-restarts on crash, and logs to journald
  sudo tee /etc/systemd/system/mlat-buyer.service > /dev/null << 'SERVICE'
[Unit]
Description=MLAT 4DSky Buyer Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/hyperplane
ExecStart=/home/ubuntu/hyperplane/main_app \
  --port=61336 \
  --mode=peer \
  --buyer-or-seller=buyer \
  --list-of-sellers-source=env \
  --envFile=.buyer-env
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mlat-buyer

[Install]
WantedBy=multi-user.target
SERVICE

  # Reload systemd and restart service
  sudo systemctl daemon-reload
  sudo systemctl enable mlat-buyer
  sudo systemctl restart mlat-buyer

  echo ""
  echo "Service status:"
  sudo systemctl status mlat-buyer --no-pager -l
REMOTE

echo ""
echo "=== Deployment complete! ==="
echo ""
echo "Useful commands to run on EC2:"
echo "  sudo journalctl -u mlat-buyer -f          # Live logs"
echo "  sudo systemctl status mlat-buyer           # Service status"
echo "  sudo systemctl restart mlat-buyer          # Restart"
echo "  sudo systemctl stop mlat-buyer             # Stop"