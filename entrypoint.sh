#!/bin/bash
# Thin wrapper that calls the Python start command
# All service orchestration logic has been moved to ibgateway/orchestrator.py

exec python3 -u /ibgateway_cli.py start-services
