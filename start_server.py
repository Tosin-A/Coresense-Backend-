#!/usr/bin/env python
"""
FastAPI server startup script for CoreSense backend.
Handles dependency checking and server startup with proper error handling.

Run from project root with: PYTHONPATH=. python backend/start_server.py
Or use the Procfile/Dockerfile which set PYTHONPATH automatically.
"""

import sys
import os
import subprocess

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
        from backend.main import app
        import uvicorn

        # Get port from environment variable (Railway sets PORT), fallback to 8000
        port = int(os.environ.get("PORT", 8000))

        print("\n🚀 Starting CoreSense backend server...")
        print(f"📡 Server will be available at: http://localhost:{port}")
        print(f"📚 API documentation: http://localhost:{port}/docs")
        print(f"🔄 Health check: http://localhost:{port}/health")
        print("\nPress Ctrl+C to stop the server")
        print("-" * 50)
        
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
        
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

