#!/bin/bash
# CoreSense Backend Startup Script
# This script handles dependency checking and starts the FastAPI server

echo "🔧 CoreSense Backend Server Startup"
echo "===================================="

# Change to backend directory
cd "$(dirname "$0")"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed or not in PATH"
    exit 1
fi

echo "✓ Python3 found: $(python3 --version)"

# Check if virtual environment exists, if not create it
if [ ! -d "venv" ]; then
    echo "📦 Virtual environment not found. Creating one..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Make the Python script executable and run it
chmod +x start_server.py
python start_server.py