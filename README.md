# IB Gateway Docker Image with noVNC and Screenshot Support

Docker image for running Interactive Brokers Gateway in a headless environment with web-based VNC access (noVNC) and screenshot capabilities.

## Features

- **Headless IB Gateway**: Runs IB Gateway under Xvfb (virtual framebuffer)
- **Web-based VNC Access**: Access the GUI via noVNC in your web browser
- **Screenshot Service**: Take screenshots and view them via HTTP API
- **Python CLI Tool**: Unified command-line interface for automation, testing, and screenshot management
- **Automation Support**: Automated GUI configuration using xdotool

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
  -p 4003:4003 \
  -p 4004:4004 \
  -it --rm ibgateway
```

### With Environment Variables

You can either use a .env file or pass them directly. Prefer .env to avoid exposing your password on the CLI. 

```bash
docker run --platform linux/amd64 \
  -v $(pwd/.env):/.env \
  -e IB_API_TYPE=IB_API \
  -e IB_TRADING_MODE=PAPER \
  -p 5900:5900 \
  -p 8080:8080 \
  -p 4003:4003 \
  -p 4004:4004 \
  -it --rm ibgateway
```

## Ports

- **5900**: noVNC web interface (access at `http://localhost:5900`)
- **8080**: Screenshot HTTP service (access at `http://localhost:8080`)
- **4003**: IB Gateway Live Trading Port (forwarded to internal port 4001)
- **4004**: IB Gateway Paper Trading Port (forwarded to internal port 4002)

**Note**: IB Gateway only accepts connections from `127.0.0.1` (localhost). The container uses `socat` to forward external ports 4003 and 4004 to the internal ports 4001 and 4002 respectively. This solves the issue of IB Gateway needing to be configured to support trusted IPs. Ports 4001 and 4002 are internal-only and should not be exposed directly from the container.

## Automation

The image includes Python-based automation for GUI interactions using xdotool. Automation is handled automatically when the container starts, or can be run manually using the CLI tool.

## Screenshot Service

The screenshot service provides an HTTP API to take and view screenshots of the IB Gateway display.


### IB Gateway Configuration

The automation system automatically configures the IB Gateway window when the container starts. You can control the configuration using:

1. **Environment variables**: Passed via `-e` flags when running the container
2. **`.env` file**: Mount a `.env` file into the container (read by the entrypoint script)

The automation will:
- Move the IB Gateway window to the top left position (0, 0)
- Configure API type (FIX or IB_API)
- Configure trading mode (LIVE or PAPER)
- Automatically type username and password into login fields (if provided)
- Log "Configuration Complete" when finished

#### Configuration Options

**Username and Password**:
- `IB_USERNAME`: IB Gateway username (optional)
- `IB_PASSWORD`: IB Gateway password (optional)

**API Type Configuration**:
- `IB_API_TYPE`: Choose between `FIX` or `IB_API` (default: `IB_API`)

**Trading Mode Configuration**:
- `IB_TRADING_MODE`: Choose between `LIVE` or `PAPER` (default: `PAPER`)

**Debug Output**:
- `DEBUG`: Enable verbose bash debug output (`1` or `true` to enable, default: `0`/disabled). When enabled, shows all commands executed during startup.

#### .env File Format

Create a `.env` file in the script directory with the following format:

```bash
IB_USERNAME=your_username
IB_PASSWORD=your_password
IB_API_TYPE=IB_API
IB_TRADING_MODE=PAPER
```

#### Examples

**Default configuration (IB API + Paper Trading)**:
```bash
docker run --platform linux/amd64 \
  -p 5900:5900 \
  -p 8080:8080 \
  -p 4003:4003 \
  -p 4004:4004 \
  -it --rm ibgateway
```

**IB API with Paper Trading (explicit)**:
```bash
docker run --platform linux/amd64 \
  -e IB_API_TYPE=IB_API \
  -e IB_TRADING_MODE=PAPER \
  -p 5900:5900 \
  -p 8080:8080 \
  -p 4003:4003 \
  -p 4004:4004 \
  -it --rm ibgateway
```

**FIX API with Live Trading and credentials**:
```bash
docker run --platform linux/amd64 \
  -e IB_USERNAME=myusername \
  -e IB_PASSWORD=mypassword \
  -e IB_API_TYPE=FIX \
  -e IB_TRADING_MODE=LIVE \
  -p 5900:5900 \
  -p 8080:8080 \
  -p 4003:4003 \
  -p 4004:4004 \
  -it --rm ibgateway
```


**Using .env file (recommended for credentials)**:
```bash
# Create .env file
cat > .env << EOF
IB_USERNAME=myusername
IB_PASSWORD=mypassword
IB_API_TYPE=IB_API
IB_TRADING_MODE=PAPER
EOF

# Run with .env file mounted
docker run --platform linux/amd64 \
  -v $(pwd)/.env:/.env \
  -p 5900:5900 \
  -p 8080:8080 \
  -p 4003:4003 \
  -p 4004:4004 \
  -it --rm ibgateway
```

## Environment Variables

- `RESOLUTION`: Display resolution (default: `1280x800`)
- `USER`: User to run as (default: `root`)
- `SCREENSHOT_PORT`: Port for screenshot HTTP server (default: `8080`)
- `IB_USERNAME`: IB Gateway username (optional, can also be set in `.env` file)
- `IB_PASSWORD`: IB Gateway password (optional, can also be set in `.env` file)
- `IB_API_TYPE`: API type - `FIX` or `IB_API` (default: `IB_API`, can also be set in `.env` file)
- `IB_TRADING_MODE`: Trading mode - `LIVE` or `PAPER` (default: `PAPER`, can also be set in `.env` file)

**Note**: Container environment variables take precedence over `.env` file values. This allows you to override specific values when needed.

## Python CLI Tool

The repository includes a Python CLI tool (`ibgateway_cli.py`) for automation, testing, and screenshot management. All commands execute inside the Docker container - no host dependencies required!

### Installation

No installation needed! Just start a container and execute commands using `docker exec`:

```bash
docker run -d --name ibgateway --platform linux/amd64 \
  -p 5900:5900 -p 8080:8080 -p 4003:4003 -p 4004:4004 \
  ibgateway:latest
```


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

**View the screenshot** by opening the returned URL in a browser or using it in markdown:
```markdown
![Screenshot](http://localhost:8080/screenshots/screenshot_20240101_120000.png)
```

Get the url from the cli
```bash
curl http://localhost:8080/screenshot/latest | jq -r '.full_url'
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

### Example: Monitoring Automation

```bash
# Take screenshot after automation starts
sleep 5
SCREENSHOT_URL=$(curl -s http://localhost:8080/screenshot | jq -r '.full_url')
echo "Screenshot available at: $SCREENSHOT_URL"

# Take periodic screenshots
while true; do
  curl -s http://localhost:8080/screenshot > /dev/null
  sleep 10
done
```

### Available Commands

**Automate IB Gateway configuration**:
```bash
docker exec ibgateway python3 /ibgateway_cli.py automate-ibgateway \
  --username myusername \
  --password mypassword \
  --api-type IB_API
```

**Take a screenshot**:
```bash
docker exec ibgateway python3 /ibgateway_cli.py screenshot --output /path/to/screenshot.png
```

**Start screenshot HTTP server**:
```bash
docker exec ibgateway python3 /ibgateway_cli.py screenshot-server --port 8080
```

**Compare two screenshots**:
```bash
docker exec ibgateway python3 /ibgateway_cli.py compare-screenshots screenshot1.png screenshot2.png
```

## Testing

**Compare screenshots**:
```bash
# Start container if not already running
docker run -d --name ibgateway --platform linux/amd64 \
  -p 5900:5900 -p 8080:8080 -p 4003:4003 -p 4004:4004 \
  ibgateway:latest

# Compare screenshots
docker exec ibgateway python3 /ibgateway_cli.py compare-screenshots screenshot1.png screenshot2.png
```

**Note**: All CLI commands must be executed inside the container using `docker exec`. Replace `ibgateway` with your container name if different.

### Automated Testing

Tests run automatically in GitHub Actions on pull requests:
- **Screenshot Service Test**: Verifies the HTTP screenshot API endpoints
- **Default Configuration Test**: Verifies IB_API + PAPER configuration
- **FIX + LIVE Test**: Verifies FIX + LIVE configuration
- **Screenshot Verification**: Takes screenshots after automation for visual verification
- **Log Verification**: Waits for "Configuration Complete" message in container logs

Test screenshots are saved to `/tmp/screenshots/` and uploaded as artifacts. They can be downloaded from the workflow run.

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
