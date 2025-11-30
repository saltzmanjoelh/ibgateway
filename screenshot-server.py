#!/usr/bin/env python3
"""
Simple HTTP server to serve screenshots and provide API to take screenshots.
Serves screenshots from /tmp/screenshots and provides endpoints:
- GET /screenshots - List all screenshots
- GET /screenshot - Take a new screenshot and return its URL
- GET /screenshot/latest - Get the latest screenshot
- GET /screenshots/<filename> - Get a specific screenshot
"""

import os
import subprocess
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import glob

SCREENSHOT_DIR = "/tmp/screenshots"
SCREENSHOT_SERVICE = "/screenshot-service.sh"

# Ensure screenshot directory exists
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


class ScreenshotHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)

        # Serve screenshot files
        if path.startswith("/screenshots/") and path != "/screenshots":
            filename = path.replace("/screenshots/", "", 1)
            # Security: Prevent path traversal attacks
            if ".." in filename or "/" in filename or "\\" in filename:
                self.send_error(400, "Invalid filename")
                return
            # Security: Only allow PNG files
            if not filename.endswith(".png"):
                self.send_error(400, "Only PNG files are allowed")
                return
            # Security: Ensure the resolved path is within SCREENSHOT_DIR
            filepath = os.path.join(SCREENSHOT_DIR, filename)
            real_path = os.path.realpath(filepath)
            real_dir = os.path.realpath(SCREENSHOT_DIR)
            if not real_path.startswith(real_dir):
                self.send_error(403, "Access denied")
                return
            if os.path.exists(filepath) and os.path.isfile(filepath):
                self.send_response(200)
                self.send_header("Content-type", "image/png")
                # Security: Restrict CORS to localhost only (container internal)
                self.send_header("Access-Control-Allow-Origin", "http://localhost")
                self.end_headers()
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Screenshot not found")
                return

        # API endpoints
        if path == "/screenshot":
            # Take a new screenshot
            try:
                result = subprocess.run(
                    [SCREENSHOT_SERVICE],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    screenshot_path = result.stdout.strip()
                    filename = os.path.basename(screenshot_path)
                    screenshot_url = f"/screenshots/{filename}"
                    
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    # Security: Restrict CORS to localhost only (container internal)
                    self.send_header("Access-Control-Allow-Origin", "http://localhost")
                    self.end_headers()
                    response = {
                        "success": True,
                        "screenshot_path": screenshot_path,
                        "filename": filename,
                        "url": screenshot_url,
                        "full_url": f"http://localhost:8080{screenshot_url}"
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_error(500, f"Screenshot failed: {result.stderr}")
            except Exception as e:
                self.send_error(500, f"Error taking screenshot: {str(e)}")
            return

        elif path == "/screenshot/latest":
            # Get the latest screenshot
            screenshots = glob.glob(os.path.join(SCREENSHOT_DIR, "screenshot_*.png"))
            if screenshots:
                latest = max(screenshots, key=os.path.getctime)
                filename = os.path.basename(latest)
                screenshot_url = f"/screenshots/{filename}"
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                # Security: Restrict CORS to localhost only (container internal)
                self.send_header("Access-Control-Allow-Origin", "http://localhost")
                self.end_headers()
                response = {
                    "success": True,
                    "screenshot_path": latest,
                    "filename": filename,
                    "url": screenshot_url,
                    "full_url": f"http://localhost:8080{screenshot_url}",
                    "created": os.path.getctime(latest)
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_error(404, "No screenshots found")
            return

        elif path == "/screenshots" or path == "/screenshots/":
            # List all screenshots
            screenshots = glob.glob(os.path.join(SCREENSHOT_DIR, "screenshot_*.png"))
            screenshots.sort(key=os.path.getctime, reverse=True)
            
            screenshot_list = []
            for screenshot in screenshots:
                filename = os.path.basename(screenshot)
                screenshot_list.append({
                    "filename": filename,
                    "url": f"/screenshots/{filename}",
                    "full_url": f"http://localhost:8080/screenshots/{filename}",
                    "created": os.path.getctime(screenshot),
                    "size": os.path.getsize(screenshot)
                })
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            # Security: Restrict CORS to localhost only (container internal)
            self.send_header("Access-Control-Allow-Origin", "http://localhost")
            self.end_headers()
            response = {
                "success": True,
                "count": len(screenshot_list),
                "screenshots": screenshot_list
            }
            self.wfile.write(json.dumps(response, indent=2).encode())
            return

        elif path == "/" or path == "/index.html":
            # Simple HTML page with API documentation and links
            html = """<!DOCTYPE html>
<html>
<head>
    <title>Screenshot Service</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
        code { background: #e0e0e0; padding: 2px 6px; border-radius: 3px; }
        a { color: #0066cc; }
    </style>
</head>
<body>
    <h1>Screenshot Service</h1>
    <p>HTTP server for taking and viewing screenshots of the IB Gateway display.</p>
    
    <h2>API Endpoints</h2>
    
    <div class="endpoint">
        <h3>GET <code>/screenshot</code></h3>
        <p>Take a new screenshot and return its URL.</p>
        <p><a href="/screenshot">Try it</a></p>
    </div>
    
    <div class="endpoint">
        <h3>GET <code>/screenshot/latest</code></h3>
        <p>Get information about the latest screenshot.</p>
        <p><a href="/screenshot/latest">Try it</a></p>
    </div>
    
    <div class="endpoint">
        <h3>GET <code>/screenshots</code></h3>
        <p>List all available screenshots.</p>
        <p><a href="/screenshots">Try it</a></p>
    </div>
    
    <div class="endpoint">
        <h3>GET <code>/screenshots/&lt;filename&gt;</code></h3>
        <p>View a specific screenshot image.</p>
    </div>
    
    <h2>Quick Actions</h2>
    <p><a href="/screenshot">Take Screenshot Now</a></p>
    <p><a href="/screenshots">View All Screenshots</a></p>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
            return

        else:
            self.send_error(404, "Not found")
            return

    def log_message(self, format, *args):
        # Custom logging to include timestamp
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")


if __name__ == "__main__":
    port = int(os.environ.get("SCREENSHOT_PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), ScreenshotHandler)
    print(f"Screenshot server starting on port {port}")
    print(f"Screenshots directory: {SCREENSHOT_DIR}")
    print(f"Access the service at: http://localhost:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nScreenshot server shutting down...")
        server.shutdown()
