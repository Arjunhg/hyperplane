#!/bin/bash
# ec2_setup_python.sh — Run this ONCE on your EC2 instance to set up Python deps
# SSH in and run: bash scripts/ec2_setup_python.sh

set -e

echo "=== Installing uv and Python dependencies for MLAT pipeline ==="

# Install uv (Astral's fast Python package manager)
if ! command -v uv &> /dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "uv already installed: $(uv --version)"
fi

# Ensure uv is on PATH for future sessions
if ! grep -q 'astral' ~/.bashrc 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

# Sync Python dependencies from pyproject.toml
cd ~/hyperplane/python
echo "Running uv sync..."
uv sync

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To run the full pipeline (buyer + MLAT solver together):"
echo ""
echo "  sudo journalctl -u mlat-buyer -f --output=cat | cd ~/hyperplane/python && uv run python -m mlat.pipeline"
echo ""
echo "Or stop the systemd service and run everything in one terminal:"
echo ""
echo "  sudo systemctl stop mlat-buyer"
echo "  cd ~/hyperplane"
echo "  ./main_app --port=61336 --mode=peer --buyer-or-seller=buyer \\"
echo "    --list-of-sellers-source=env --envFile=.buyer-env 2>&1 | cd python && uv run python -m mlat.pipeline"