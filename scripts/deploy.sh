#!/bin/bash
# deploy.sh — Sync local code to EC2 and restart the buyer service
# Usage: ./deploy.sh
# Requirements: hederakeypair.pem in project root, EC2_HOST set below

set -e

# ── CONFIG ──────────────────────────────────────────────────────────────────
EC2_HOST="${EC2_HOST:-ubuntu@your-ec2-host}"
PEM="${PEM:-your-key.pem}"
REMOTE_DIR="${REMOTE_DIR:-~/your-app-dir}"
SERVICE_NAME="${SERVICE_NAME:-your-service}"
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

  # Install systemd service file (source of truth: systemd/mlat-buyer.service)
  echo "Installing systemd service file..."
REMOTE

scp -i "$PEM" systemd/mlat-buyer.service "$EC2_HOST:/tmp/mlat-buyer.service"
ssh -i "$PEM" "$EC2_HOST" << 'REMOTE'
  set -e
  sudo mv /tmp/mlat-buyer.service /etc/systemd/system/mlat-buyer.service

  # Reload systemd and restart service
  sudo systemctl daemon-reload
  # sudo systemctl enable mlat-buyer
  # sudo systemctl restart mlat-buyer

  # use ENV=prod ./deploy.sh to enable auto-restart, otherwise just print instructions
  if [ "$ENV" = "prod" ]; then
    echo "Production environment detected, restarting service..."
    sudo systemctl enable mlat-buyer
    sudo systemctl restart mlat-buyer
  else
    echo "Non-production environment, skipping service restart. Please restart manually if needed using '
      cd ~/hyperplane
      ./main_app --port=61336 --mode=peer --buyer-or-seller=buyer \
        --list-of-sellers-source=env --envFile=.buyer-env
    '."
  fi
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