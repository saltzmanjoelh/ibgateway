# IB Gateway Docker Image with noVNC and Screenshot Support

Docker image for running Interactive Brokers Gateway in a headless environment with web-based VNC access (noVNC) and screenshot capabilities.

## Features

- **Headless IB Gateway**: Runs IB Gateway under Xvfb (virtual framebuffer)
- **Web-based VNC Access**: Access the GUI via noVNC in your web browser
- **Screenshot Service**: Take screenshots and view them via HTTP API
- **Automation Support**: Includes automation scripts for GUI interactions

## Building

```bash
docker build --platform linux/amd64 -t ibgateway .
```

**Note**: IB Gateway requires x86_64 architecture, so use `--platform linux/amd64` when building.

## Running

### Basic Usage

```bash
docker run --platform linux/amd64 \
  -p 5900:5900 \
  -p 8080:8080 \
  -it --rm ibgateway
```

### With Volume Mounts (for custom scripts)

```bash
docker run --platform linux/amd64 \
  -v $(pwd)/automate-ibgateway.sh:/automate-ibgateway.sh \
  -p 5900:5900 \
  -p 8080:8080 \
  -it --rm ibgateway
```

## Ports

- **5900**: noVNC web interface (access at `http://localhost:5900`)
- **8080**: Screenshot HTTP service (access at `http://localhost:8080`)

## Screenshot Service

The screenshot service provides an HTTP API to take and view screenshots of the IB Gateway display.

### API Endpoints

#### Take a Screenshot
```bash
curl http://localhost:8080/screenshot
```

Returns JSON with screenshot information:
```json
{
  "success": true,
  "screenshot_path": "/tmp/screenshots/screenshot_20240101_120000.png",
  "filename": "screenshot_20240101_120000.png",
  "url": "/screenshots/screenshot_20240101_120000.png",
  "full_url": "http://localhost:8080/screenshots/screenshot_20240101_120000.png"
}
```

#### Get Latest Screenshot
```bash
curl http://localhost:8080/screenshot/latest
```

#### List All Screenshots
```bash
curl http://localhost:8080/screenshots
```

#### View a Screenshot Image
```bash
# Direct image URL (use in browser or img tag)
http://localhost:8080/screenshots/screenshot_20240101_120000.png
```

### Web Interface

Access the screenshot service web interface at:
```
http://localhost:8080/
```

This provides a simple HTML page with API documentation and quick links.

### Usage from Cursor Web Agent

When working on automation scripts, you can:

1. **Take a screenshot**:
   ```bash
   curl http://localhost:8080/screenshot
   ```

2. **Get the latest screenshot URL**:
   ```bash
   curl http://localhost:8080/screenshot/latest | jq -r '.full_url'
   ```

3. **View the screenshot** by opening the returned URL in a browser or using it in markdown:
   ```markdown
   ![Screenshot](http://localhost:8080/screenshots/screenshot_20240101_120000.png)
   ```

### Example: Monitoring Automation Script

```bash
# Run automation script
./automate-ibgateway.sh &

# Take screenshot after script starts
sleep 5
SCREENSHOT_URL=$(curl -s http://localhost:8080/screenshot | jq -r '.full_url')
echo "Screenshot available at: $SCREENSHOT_URL"

# Take periodic screenshots
while true; do
  curl -s http://localhost:8080/screenshot > /dev/null
  sleep 10
done
```

## Automation

The image includes automation scripts for GUI interactions:

- `automate-ibgateway.sh`: Script using xdotool to automatically configure IB Gateway window
- `run-ibgateway.sh`: Script to run IB Gateway under Xvfb

### IB Gateway Configuration

The `automate-ibgateway.sh` script automatically configures the IB Gateway window when it starts. You can control the configuration using environment variables:

#### API Type Configuration

- `IB_API_TYPE`: Choose between `FIX` or `IB_API` (default: `IB_API`)

#### Trading Mode Configuration

- `IB_TRADING_MODE`: Choose between `LIVE` or `PAPER` (default: `PAPER`)

#### Examples

**Default configuration (IB API + Paper Trading)**:
```bash
docker run --platform linux/amd64 \
  -p 5900:5900 \
  -p 8080:8080 \
  -it --rm ibgateway
```

**FIX API with Live Trading**:
```bash
docker run --platform linux/amd64 \
  -e IB_API_TYPE=FIX \
  -e IB_TRADING_MODE=LIVE \
  -p 5900:5900 \
  -p 8080:8080 \
  -it --rm ibgateway
```

**IB API with Paper Trading (explicit)**:
```bash
docker run --platform linux/amd64 \
  -e IB_API_TYPE=IB_API \
  -e IB_TRADING_MODE=PAPER \
  -p 5900:5900 \
  -p 8080:8080 \
  -v $(pwd)/automate-ibgateway.sh:/automate-ibgateway.sh \
  -it --rm ibgateway
```

## Environment Variables

- `RESOLUTION`: Display resolution (default: `1280x800`)
- `USER`: User to run as (default: `root`)
- `SCREENSHOT_PORT`: Port for screenshot HTTP server (default: `8080`)
- `IB_API_TYPE`: API type - `FIX` or `IB_API` (default: `IB_API`)
- `IB_TRADING_MODE`: Trading mode - `LIVE` or `PAPER` (default: `PAPER`)

## Testing

The repository includes test scripts to verify automation functionality:

### Local Testing

**Test automation script** (requires running container):
```bash
# Start container first
docker run -d --name ibgateway-test --platform linux/amd64 -p 5900:5900 -p 8080:8080 ibgateway-test:latest

# Run automation tests
./test-automation.sh ibgateway-test
```

**CI-friendly test script**:
```bash
./test-automation-ci.sh ibgateway-test
```

**Compare screenshots** (optional, requires Pillow):
```bash
pip install Pillow
./compare-screenshots.py screenshot1.png screenshot2.png
```

### Automated Testing

Tests run automatically in GitHub Actions on pull requests:
- **Default Configuration Test**: Verifies IB_API + PAPER configuration
- **FIX + LIVE Test**: Verifies FIX + LIVE configuration
- **Screenshot Verification**: Takes screenshots after automation for visual verification
- **Log Verification**: Checks container logs for automation completion messages

Test screenshots are uploaded as artifacts and can be downloaded from the workflow run.

## Troubleshooting

### VNC Connection Issues

Check if the VNC server is running:
```bash
docker exec <container_id> netstat -tlnp | grep 5901
```

### Screenshot Service Not Available

Check if the screenshot server is running:
```bash
docker exec <container_id> netstat -tlnp | grep 8080
```

View logs:
```bash
docker logs <container_id>
```

## License

See LICENSE file for details.
