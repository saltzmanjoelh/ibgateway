# Testing Square Artifacts on Screen

## Quick Test Instructions

To see the square artifacts in action:

1. **Build the Docker image:**
   ```bash
   docker build --platform linux/amd64 -t ibgateway-test:latest .
   ```

2. **Run the container:**
   ```bash
   docker run -d \
     --name ibgateway-test \
     --platform linux/amd64 \
     -p 5900:5900 \
     -p 8080:8080 \
     -e IB_API_TYPE=IB_API \
     -e IB_TRADING_MODE=PAPER \
     ibgateway-test:latest
   ```

3. **Wait for automation to complete** (about 10-15 seconds)

4. **Take a screenshot:**
   ```bash
   curl http://localhost:8080/screenshot
   ```
   
   Or view it in browser: http://localhost:8080/screenshot

5. **View the screenshot:**
   ```bash
   curl http://localhost:8080/screenshot/latest | jq -r '.url' | xargs -I {} curl http://localhost:8080{} -o screenshot.png
   ```

## What to Expect

You should see **red square artifacts** (25x25 pixels) at:
- **(~350, ~175)** - API Type button click location
- **(~500, ~275)** - Trading Mode button click location

The squares will be visible for 10 seconds after being drawn, giving you time to take screenshots.

## Manual Test Script

You can also test the square drawing directly:

```bash
# Inside the container
docker exec -it ibgateway-test bash
export DISPLAY=:99
python3 /draw-square-on-screen.py 100 100 30 red 5.0 :99
```

## Troubleshooting

- If squares don't appear, check that `python3-tkinter` is installed
- Verify X11 display is running: `echo $DISPLAY` should show `:99`
- Check container logs: `docker logs ibgateway-test`
