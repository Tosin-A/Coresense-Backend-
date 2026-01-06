# CoreSense Backend Setup Guide

This guide will help you set up and run the CoreSense backend server on your system.

## Prerequisites

- Python 3.14.0 or higher
- pip package manager

## Quick Start

### Option 1: Automatic Setup (Recommended)

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Run the setup script:
   ```bash
   chmod +x setup_env.sh
   ./setup_env.sh
   ```

3. Start the server:
   ```bash
   ./start.sh
   ```

### Option 2: Manual Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv venv
   ```

3. Activate the virtual environment:
   ```bash
   source venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Start the server:
   ```bash
   python start_server.py
   ```

## Server Information

Once started, the server will be available at:
- **API Endpoint**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Troubleshooting

### "permission denied" Error
If you get this error when running shell scripts, make them executable first:
```bash
chmod +x setup_env.sh start.sh
```

### "command not found: python"
If you get this error, your system may only have `python3` available. Use:
```bash
python3 start_server.py
```

### "externally-managed-environment" Error
This occurs when using Homebrew's Python installation. The setup script handles this automatically by creating a virtual environment.

### Missing Dependencies
If dependencies are missing, the startup script will attempt to install them automatically. If this fails, install manually:
```bash
pip install fastapi uvicorn supabase openai
```

## Stopping the Server

To stop the server, press `Ctrl+C` in the terminal where it's running.

## Files Overview

- `start_server.py` - Main Python startup script
- `start.sh` - Shell script that handles virtual environment setup and startup
- `setup_env.sh` - Environment setup script (creates virtual environment and installs dependencies)
- `requirements.txt` - Python package dependencies
- `config.py` - Application configuration
- `main.py` - FastAPI application entry point