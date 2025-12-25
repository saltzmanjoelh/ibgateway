#!/bin/bash
# Thin wrapper that calls the Python start command
# All service orchestration logic has been moved to ibgateway/orchestrator.py
set -e
# Check if debug mode is enabled
if [ "${DEBUG}" = "1" ] || [ "${DEBUG}" = "true" ]; then
    # Start with debugpy for remote debugging
    # Use PYTHONUNBUFFERED instead of -u flag for unbuffered output
    export PYTHONUNBUFFERED=1
    exec python3 -m debugpy --listen 0.0.0.0:5678 --wait-for-client /ibgateway_manager_cli.py start-services
else
    # Run normally
    exec python3 -u /ibgateway_manager_cli.py start-services
fi
