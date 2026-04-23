#!/bin/bash
# deploy.sh � Sync local code to EC2 and restart services
# Usage: ./deploy.sh

set -e

# Config (override via environment variables)
# EC2_HOST="${EC2_HOST:-ubuntu@your-ec2-host}"
# PEM="${PEM:-your-key.pem}"
# REMOTE_DIR="${REMOTE_DIR:-~/your-app-dir}"
# SERVICE_NAME="${SERVICE_NAME:-your-service}"
EC2_HOST="ubuntu@ec2-13-220-54-53.compute-1.amazonaws.com"
# PEM="hederakeypair.pem" For bash
PEM="$HOME/.ssh/hederakeypair.pem" # For WSL
REMOTE_DIR="~/hyperplane"
SERVICE_NAME="mlat-buyer"

echo "=== Step 0: Building frontend (web/dist) ==="
if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is required to build the frontend before deployment."
  exit 1
fi
pnpm --dir web install --frozen-lockfile
pnpm --dir web build

EXCLUDES="--exclude='.git'"
if [ -f ".gitignore" ]; then
  while IFS= read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    EXCLUDES="$EXCLUDES --exclude='$line'"
  done < ".gitignore"
fi

# Always exclude sensitive files from tar stream
echo "=== Step 1: Syncing project files to EC2 ==="
rsync -avz --delete \
  -e "ssh -T -i $PEM" \
  --exclude='.git' \
  --exclude='.buyer-env' \
  --exclude='*.pem' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  --exclude='python/tests' \
  --exclude='docs' \
  --exclude='*.md' \
  --exclude='*.bak' \
  --exclude='web/node_modules' \
  -e "ssh -i $PEM" \
  . "$EC2_HOST:$REMOTE_DIR"


echo "Uploading secrets..."
scp -i "$PEM" .buyer-env "$EC2_HOST:$REMOTE_DIR/.buyer-env"
scp -i "$PEM" location-override.json "$EC2_HOST:$REMOTE_DIR/location-override.json"

echo "Uploading built frontend dist..."
ssh -i "$PEM" "$EC2_HOST" "rm -rf $REMOTE_DIR/web/dist && mkdir -p $REMOTE_DIR/web"
scp -r -i "$PEM" web/dist "$EC2_HOST:$REMOTE_DIR/web/"

echo ""
echo "=== Step 2: Build and install systemd service on EC2 ==="

ssh -i "$PEM" "$EC2_HOST" "ENV=$ENV bash -s" << 'REMOTE'
  set -e
  cd ~/hyperplane

  export PATH=$PATH:/usr/local/go/bin

  echo "Building Go binary..."
  go build -o main_app .
  echo "Build successful."

  echo "Installing systemd service file..."
REMOTE

scp -i "$PEM" systemd/mlat-buyer.service "$EC2_HOST:/tmp/mlat-buyer.service"
ssh -i "$PEM" "$EC2_HOST" << 'REMOTE'
  set -e
  sudo mv /tmp/mlat-buyer.service /etc/systemd/system/mlat-buyer.service

  sudo systemctl daemon-reload

  if [ "$ENV" = "prod" ]; then
    echo "Production environment detected, restarting service..."
    sudo systemctl enable mlat-buyer
    sudo systemctl restart mlat-buyer
  else
    echo "Non-production environment, skipping service restart. Start manually if needed:"
    echo "  cd ~/hyperplane"
    echo "  ./main_app --port=61336 --mode=peer --buyer-or-seller=buyer --list-of-sellers-source=env --envFile=.buyer-env"
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