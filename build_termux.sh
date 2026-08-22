#!/bin/bash
# Build script for Termux/Android deployment
# Creates a standalone executable from Python source

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "Facebook Auto Poster - Termux Build Script"
echo "================================================"
echo ""

# Detect architecture
ARCH=$(uname -m)
echo "Architecture: $ARCH"

# Check if we're on a compatible system
if [[ "$ARCH" != "aarch64" && "$ARCH" != "armv8l" && "$ARCH" != "x86_64" ]]; then
    echo "Warning: Unexpected architecture: $ARCH"
fi

# Check Python version
PYTHON_VER=$(python3 -c "import sys; print(sys.version_info.major * 100 + sys.version_info.minor)")
echo "Python version: $PYTHON_VER"

# Install build dependencies if needed
echo ""
echo "Checking/installing build dependencies..."

if ! command -v pyinstaller &> /dev/null; then
    echo "Installing PyInstaller..."
    pip install pyinstaller --quiet
fi

# Verify requirements
echo ""
echo "Verifying dependencies..."
pip list 2>/dev/null | grep -E "requests|rich|apscheduler|facebook-business" > /dev/null || echo "Warning: Some dependencies may be missing"

# Clean previous builds
echo ""
echo "Cleaning previous builds..."
rm -rf build/ dist/ *.spec 2>/dev/null || true

# Build with PyInstaller
echo ""
echo "Building standalone executable..."
echo ""

pyinstaller \
    --onefile \
    --name "fb_poster" \
    --add-data "src:src" \
    --hidden-import "src" \
    --hidden-import "src.config.manager" \
    --hidden-import "src.facebook.client" \
    --hidden-import "src.facebook.poster" \
    --hidden-import "src.content.manager" \
    --hidden-import "src.scheduler.manager" \
    --hidden-import "src.downloader.manager" \
    --hidden-import "src.creator.sync_manager" \
    --hidden-import "src.creator.queue_manager" \
    --hidden-import "src.ui.console" \
    --hidden-import "src.ui.prompts" \
    --hidden-import "src.ui.setup_prompts" \
    --hidden-import "src.ui.messages" \
    --hidden-import "src.utils.logger" \
    --hidden-import "src.utils.notifications" \
    --collect-all "apscheduler" \
    --clean \
    main.py 2>&1 | tee build.log

# Check if build succeeded
if [ -f "dist/fb_poster" ]; then
    echo ""
    echo "Build successful!"
    echo ""

    # Create release directory
    mkdir -p release
    cp dist/fb_poster release/

    # Create minimal README
    cat > release/README.md << 'EOF'
# Facebook Auto Poster - Android/Termux

## Installation

```bash
chmod +x fb_poster
./fb_poster
```

## Prerequisites

```bash
pkg install -y ffmpeg yt-dlp python
```

## Usage

```bash
# Run interactively
./fb_poster

# Post immediately
./fb_poster --post-now <content_id>

# Download content
./fb_poster --download <url>

# Update credentials
./fb_poster --update-credentials
```
EOF

    # Copy build instructions
    if [ -f "BUILD_INSTRUCTIONS.md" ]; then
        cp BUILD_INSTRUCTIONS.md release/
    fi

    # Copy install script
    if [ -f "INSTALL_TERMUX.sh" ]; then
        cp INSTALL_TERMUX.sh release/
    fi

    echo "Created release package:"
    ls -lh release/
    echo ""
    echo "Binary size: $(du -h release/fb_poster | cut -f1)"
    echo ""
    echo "To upload to GitHub:"
    echo "  git add release/fb_poster"
    echo "  git commit -m 'Add prebuilt Android binary'"
    echo "  git push"

else
    echo ""
    echo "Build failed! Check build.log for details."
    exit 1
fi

echo ""
echo "Build complete!"