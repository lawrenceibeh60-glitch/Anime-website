#!/usr/bin/env bash
set -euo pipefail
echo '========================================'
echo 'KYRO AI Anime - Build Script Starting'
echo '========================================'
echo '[1/4] Updating apt package lists...'
apt-get update -qq || { echo 'WARNING: apt-get update failed, continuing anyway...'; }
echo '[2/4] Installing ffmpeg...'
apt-get install -y -qq ffmpeg || { echo 'ERROR: ffmpeg installation failed!'; }
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version | head -n 1)
    echo "SUCCESS: ffmpeg installed - $FFMPEG_VERSION"
else
    echo 'WARNING: ffmpeg not found after installation attempt'
fi
echo '[3/4] Installing Python packages...'
pip install -r requirements.txt --no-cache-dir
python -c "import flask; print(f'Flask {flask.__version__}')" || echo 'WARNING: Flask import failed'
python -c "import requests; print(f'Requests {requests.__version__}')" || echo 'WARNING: requests import failed'
python -c "import bs4; print('BeautifulSoup4 ready')" || echo 'WARNING: BeautifulSoup4 import failed'
echo '[4/4] Verifying app.py...'
if [ -f 'app.py' ]; then
    python -m py_compile app.py && echo 'SUCCESS: app.py syntax OK' || echo 'WARNING: app.py has syntax errors'
else
    echo 'ERROR: app.py not found!'
    exit 1
fi
echo '========================================'
echo 'KYRO AI Anime - Build Complete!'
echo '========================================'

