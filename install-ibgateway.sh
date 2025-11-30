#!/bin/bash
# Install IB Gateway in the background
# This script can be run independently or from entrypoint.sh

set -x

echo "=== Starting IB Gateway installation ==="
curl https://download2.interactivebrokers.com/installers/ibgateway/latest-standalone/ibgateway-latest-standalone-linux-x64.sh > /tmp/install-ibgateway.sh
chmod +x /tmp/install-ibgateway.sh
/tmp/install-ibgateway.sh -q -f /tmp/install-ibgateway.log

echo "=== IB Gateway installation completed ==="
echo "Installation log available at /tmp/install-ibgateway.log"

