"""
HTTP server for screenshot API.
"""

import os
import json
import glob
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from .screenshot import ScreenshotHandler
from .config import Config


class ScreenshotServer(BaseHTTPRequestHandler):
    """HTTP server for screenshot API."""
    
    screenshot_handler = None
    screenshot_dir = "/tmp/screenshots"
    
    @classmethod
    def run_server(cls, config: Config, port: int, verbose: bool = False) -> int:
        """Run the screenshot HTTP server.
        
        Args:
            config: Configuration object
            port: Port to listen on
            verbose: Enable verbose output
            
        Returns:
            Exit code (0 on success)
        """
        cls.screenshot_handler = ScreenshotHandler(config, verbose)
        cls.screenshot_dir = config.screenshot_dir
        
        server = HTTPServer(("0.0.0.0", port), cls)
        print(f"Screenshot server starting on port {port}")
        print(f"Screenshots directory: {config.screenshot_dir}")
        print(f"Access the service at: http://localhost:{port}/")
        print(f"--- Screenshot service ready on port {port} ---")
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nScreenshot server shutting down...")
            server.shutdown()
        
        return 0
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Serve screenshot files
        if path.startswith("/screenshots/") and path != "/screenshots":
            self._serve_screenshot_file(path)
            return
        
        # API endpoints
        if path == "/screenshot":
            self._handle_take_screenshot()
        elif path == "/screenshot/latest":
            self._handle_latest_screenshot()
        elif path == "/screenshots" or path == "/screenshots/":
            self._handle_list_screenshots()
        elif path == "/" or path == "/index.html":
            self._handle_index()
        else:
            self.send_error(404, "Not found")
    
    def _serve_screenshot_file(self, path: str):
        """Serve a screenshot file."""
        filename = path.replace("/screenshots/", "", 1)
        
        # Security checks
        if ".." in filename or "/" in filename or "\\" in filename:
            self.send_error(400, "Invalid filename")
            return
        
        if not filename.endswith(".png"):
            self.send_error(400, "Only PNG files are allowed")
            return
        
        filepath = os.path.join(self.screenshot_dir, filename)
        real_path = os.path.realpath(filepath)
        real_dir = os.path.realpath(self.screenshot_dir)
        
        if not real_path.startswith(real_dir):
            self.send_error(403, "Access denied")
            return
        
        if os.path.exists(filepath) and os.path.isfile(filepath):
            self.send_response(200)
            self.send_header("Content-type", "image/png")
            self.send_header("Access-Control-Allow-Origin", "http://localhost")
            self.end_headers()
            with open(filepath, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, "Screenshot not found")
    
    def _handle_take_screenshot(self):
        """Handle /screenshot endpoint - take a new screenshot."""
        if not self.screenshot_handler:
            self.send_error(500, "Screenshot handler not configured")
            return
        
        try:
            screenshot_path = self.screenshot_handler.take_screenshot()
            if screenshot_path:
                filename = os.path.basename(screenshot_path)
                screenshot_url = f"/screenshots/{filename}"
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "http://localhost")
                self.end_headers()
                
                response = {
                    "success": True,
                    "screenshot_path": screenshot_path,
                    "filename": filename,
                    "url": screenshot_url,
                    "full_url": f"http://localhost:{self.server.server_port}{screenshot_url}"
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_error(500, "Failed to take screenshot")
        except Exception as e:
            self.send_error(500, f"Error taking screenshot: {str(e)}")
    
    def _handle_latest_screenshot(self):
        """Handle /screenshot/latest endpoint."""
        screenshots = glob.glob(os.path.join(self.screenshot_dir, "screenshot_*.png"))
        if screenshots:
            latest = max(screenshots, key=os.path.getctime)
            filename = os.path.basename(latest)
            screenshot_url = f"/screenshots/{filename}"
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "http://localhost")
            self.end_headers()
            
            response = {
                "success": True,
                "screenshot_path": latest,
                "filename": filename,
                "url": screenshot_url,
                "full_url": f"http://localhost:{self.server.server_port}{screenshot_url}",
                "created": os.path.getctime(latest)
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_error(404, "No screenshots found")
    
    def _handle_list_screenshots(self):
        """Handle /screenshots endpoint - list all screenshots."""
        screenshots = glob.glob(os.path.join(self.screenshot_dir, "screenshot_*.png"))
        screenshots.sort(key=os.path.getctime, reverse=True)
        
        screenshot_list = []
        for screenshot in screenshots:
            filename = os.path.basename(screenshot)
            screenshot_list.append({
                "filename": filename,
                "url": f"/screenshots/{filename}",
                "full_url": f"http://localhost:{self.server.server_port}/screenshots/{filename}",
                "created": os.path.getctime(screenshot),
                "size": os.path.getsize(screenshot)
            })
        
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "http://localhost")
        self.end_headers()
        
        response = {
            "success": True,
            "count": len(screenshot_list),
            "screenshots": screenshot_list
        }
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def _handle_index(self):
        """Handle root endpoint - serve HTML documentation."""
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
    
    def log_message(self, format, *args):
        """Custom logging with timestamp."""
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

