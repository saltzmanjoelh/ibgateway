#!/bin/bash
# Thin wrapper that calls the Python start command
# All service orchestration logic has been moved to ibgateway/orchestrator.py

exec python3 -u /ibgateway_manager_cli.py start-services --no-automation
