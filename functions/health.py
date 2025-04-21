from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "message": "Trade Analysis API is running"
        }
        
        self.wfile.write(json.dumps(response_data).encode()) 