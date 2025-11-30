#!/bin/bash
set -e
export DISPLAY=:99
Xvfb :99 -screen 0 ${RESOLUTION}x24 -ac +extension GLX +render -noreset &
sleep 2
/opt/ibgateway/ibgateway &
sleep 15