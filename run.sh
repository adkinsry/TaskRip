#!/usr/bin/env bash
# Launch the Task Manager application.
# Requires: pip install -r requirements.txt
# Also requires: tesseract-ocr (apt install tesseract-ocr on Ubuntu/Debian)

set -e
cd "$(dirname "$0")"
python3 -m taskmanager.main
