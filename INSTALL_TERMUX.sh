#!/bin/bash
# Termux Installation Script for Facebook Auto Poster
# This script sets up the complete runtime environment

set -e

echo "============================================"
echo "Facebook Auto Poster - Termux Install"
echo "============================================"
echo ""

# 1. Update package lists
echo "[1/6] Updating package lists..."
pkg update -y && pkg upgrade -y

# 2. Install Python and build tools
echo "[2/6] Installing Python and build tools..."
pkg install -y python clang make openssl-dev libffi-dev zlib-dev libxml2-dev

# 3. Install FFmpeg (required for video processing)
echo "[3/6] Installing FFmpeg..."
pkg install -y ffmpeg

# 4. Install yt-dlp
echo "[4/6] Installing yt-dlp..."
pip install yt-dlp --quiet

# 5. Install Python dependencies
echo "[5/6] Installing Python packages..."
pip install \
    requests \
    rich \
    questionary \
    apscheduler \
    facebook-business \
    python-dotenv \
    python-dateutil \
    pytz \
    pyyaml \
    tqdm \
    colorama \
    click --quiet

# 6. Verify installation
echo "[6/6] Verifying installation..."
echo ""
echo "Python version: $(python --version)"
echo "FFmpeg version: $(ffmpeg -version 2>/dev/null | head -1 || echo 'not found')"
echo "yt-dlp version: $(yt-dlp --version 2>/dev/null || echo 'not found')"
echo ""

echo "============================================"
echo "Installation Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Download fb_poster from: https://github.com/YOUR_USERNAME/fb-cloning/releases"
echo "  2. chmod +x fb_poster"
echo "  3. ./fb_poster"
echo ""
echo "Or if you have the full repository:"
echo "  cd fb-cloning"
echo "  python main.py"