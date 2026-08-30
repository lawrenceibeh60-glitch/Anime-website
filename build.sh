#!/usr/bin/env bash
# KYRO AI Anime Downloader - Render.com Build Script
# =============================================================================
set -eo pipefail

echo '========================================'
echo 'KYRO AI Anime - Build Script Starting'
echo '========================================'

# Step 1: Check ffmpeg (Render's Python image has it pre-installed)
echo '[1/3] Checking ffmpeg...'
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version | head -n 1)
    echo "SUCCESS: ffmpeg available - ${FFMPEG_VERSION}"
else
    echo "WARNING: ffmpeg not found - quality transcoding disabled"
fi

# Step 2: Ensure templates directory exists and index.html is in place
echo '[2/3] Setting up templates...'
mkdir -p templates
if [ -f "index.html" ]; then
    cp index.html templates/index.html
    echo "SUCCESS: index.html copied to templates/"
fi
if [ -f "dashboard.html" ]; then
    cp dashboard.html templates/dashboard.html
    echo "SUCCESS: dashboard.html copied to templates/"
fi
if [ -f "remote_controller.html" ]; then
    cp remote_controller.html templates/remote_controller.html
    echo "SUCCESS: remote_controller.html copied to templates/"
fi

# Step 3: Install Python packages
echo '[3/3] Installing Python packages...'
pip install -r requirements.txt --no-cache-dir

echo 'Verifying packages...'
python -c "import flask; print(f'Flask {flask.__version__}')"
python -c "import requests; print(f'Requests OK')"
python -c "import bs4; print('BeautifulSoup4 ready')"
python -c "import user_agents; print('User-Agents ready')"

echo '========================================'
echo 'KYRO AI Anime - Build Complete!'
echo '========================================'
