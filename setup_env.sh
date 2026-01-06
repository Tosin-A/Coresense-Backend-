#!/bin/bash
# CoreSense Backend Environment Setup Script
# Creates a virtual environment and installs dependencies

echo "🔧 Setting up CoreSense Backend Environment"
echo "=========================================="

# Change to backend directory
cd "$(dirname "$0")"

# Check if Python3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed or not in PATH"
    exit 1
fi

echo "✓ Python3 found: $(python3 --version)"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📦 Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "✅ Environment setup complete!"
echo ""
echo "To start the server, run:"
echo "  source venv/bin/activate"
echo "  python start_server.py"
echo ""
echo "Or use the startup script:"
echo "  ./start.sh"