#!/usr/bin/env python
"""
FastAPI server startup script for CoreSense backend.
Handles dependency checking and server startup with proper error handling.
"""

import sys
import os
import subprocess
from pathlib import Path

# Add parent directory to Python path so we can import 'backend' module
# This allows absolute imports like 'from backend.config import ...'
backend_dir = Path(__file__).parent
parent_dir = backend_dir.parent
sys.path.insert(0, str(parent_dir))

def check_dependencies():
    """Check if required dependencies are available."""
    required_packages = [
        'fastapi',
        'uvicorn', 
        'supabase',
        'openai'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} is available")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} is missing")
    
    return missing_packages

def install_missing_dependencies(packages):
    """Attempt to install missing dependencies."""
    if not packages:
        return True
    
    print(f"\nAttempting to install missing packages: {', '.join(packages)}")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            *packages, "--user", "--quiet"
        ])
        print("Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("Failed to install dependencies. Please install manually:")
        print(f"pip install {' '.join(packages)}")
        return False

def start_server():
    """Start the FastAPI server."""
    try:
        # Check dependencies
        missing = check_dependencies()
        
        if missing:
            if not install_missing_dependencies(missing):
                print("\nPlease install missing dependencies and try again.")
                print(f"pip install {' '.join(missing)}")
                return False
        
        # Import and start the FastAPI app
        from main import app
        import uvicorn
        
        print("\n🚀 Starting CoreSense xabackend server...")
        print("📡 Server will be available at: http://localhost:8000")
        print("📚 API documentation: http://localhost:8000/docs")
        print("🔄 Health check: http://localhost:8000/health")
        print("\nPress Ctrl+C to stop the server")
        print("-" * 50)
        
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🔧 CoreSense Backend Server Startup")
    print("=" * 40)
    
    success = start_server()
    
    if not success:
        sys.exit(1)