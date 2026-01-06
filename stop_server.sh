#!/bin/bash
# Stop the backend server if it's running on port 8000

echo "Checking for process on port 8000..."
PID=$(lsof -ti:8000)

if [ -z "$PID" ]; then
    echo "No process found on port 8000"
    exit 0
fi

echo "Found process $PID on port 8000"
kill -9 $PID
echo "Killed process $PID"

sleep 1
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "Warning: Port 8000 is still in use"
else
    echo "✅ Port 8000 is now free"
fi





