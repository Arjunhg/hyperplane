#!/bin/bash
# ec2_setup_python.sh — Run this ONCE on your EC2 instance to set up Python deps
# SSH in and run: bash ec2_setup_python.sh

set -e

echo "=== Installing Python dependencies for MLAT pipeline ==="

# Install pip if not present
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-venv

# Create venv in the project directory
cd ~/hyperplane
python3 -m venv mlat-env
source mlat-env/bin/activate

# Install packages
pip install --upgrade pip
pip install numpy scipy pyModeS

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To run the full pipeline (buyer + MLAT solver together):"
echo ""
echo "  source ~/hyperplane/mlat-env/bin/activate"
echo "  sudo journalctl -u mlat-buyer -f --output=cat | python3 ~/hyperplane/mlat_pipeline.py"
echo ""
echo "Or stop the systemd service and run everything in one terminal:"
echo ""
echo "  sudo systemctl stop mlat-buyer"
echo "  cd ~/hyperplane"
echo "  source mlat-env/bin/activate"
echo "  ./main_app --port=61336 --mode=peer --buyer-or-seller=buyer \\"
echo "    --list-of-sellers-source=env --envFile=.buyer-env 2>&1 | python3 mlat_pipeline.py"