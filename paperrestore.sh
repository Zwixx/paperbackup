#!/bin/bash

# Wrapper script for paperrestore.py
# Allows calling: paperrestore.sh backup.pdf [password]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/paperrestore.py"

# Handle arguments
PDF_FILE="$1"
PASSWORD="$2"

if [ -z "$PDF_FILE" ]; then
    echo "Usage: paperrestore.sh backup.pdf [password]"
    echo "  backup.pdf: PDF file created by paperbackup.py"
    echo "  password: (optional) password for encrypted backup"
    exit 1
fi

# Find Python executable - try python3 first, then python
PYTHON_CMD=""
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "Error: Python not found. Please install Python 3"
    exit 1
fi

# Call Python script
if [ -n "$PASSWORD" ]; then
    "$PYTHON_CMD" "$PYTHON_SCRIPT" "$PDF_FILE" --password "$PASSWORD"
else
    "$PYTHON_CMD" "$PYTHON_SCRIPT" "$PDF_FILE"
fi
