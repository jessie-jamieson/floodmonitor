from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import urllib.request
import json

class USGSProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Serve the HTML file for root requests
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            try:
                with open('index.html', 'rb') as file:
                    self.wfile.write(file.read())
            except FileNotFoundError:
                self.wfile.write(b"<html><body><h1>Error: index.html not found</h1></body></html>")
            return
            
        # Handle API proxy requests
        elif self.path.startswith('/api/usgs'):
            # Parse query parameters
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            # Get bbox parameter
            bbox = params.get('bbox', [''])[0]
            parameter_cd = params.get('parameterCd', ['00065,00060'])[0]
            
            if not bbox:
                self.send_error(400, "Missing bbox parameter")
                return
                
            # Construct USGS API URL
            usgs_url = f"https://waterservices.usgs.gov/nwis/iv/?format=json&bBox={bbox}&parameterCd={parameter_cd}&siteStatus=active"
            
            try:
                print(f"Proxying request to USGS with bbox: {bbox}")
                
                # Set up the request with a custom User-Agent
                headers = {
                    'User-Agent': 'FloodMapApp/1.0 (Contact: your.email@example.com)'
                }
                req = urllib.request.Request(usgs_url, headers=headers)
                
                # Make the request to USGS API
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read()
                    
                    # Send success response
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')  # CORS header
                    self.end_headers()
                    self.wfile.write(data)
                    
                    # Log success
                    print("Successfully proxied USGS data")
                    
            except Exception as e:
                print(f"Error fetching USGS data: {str(e)}")
                
                # Send error response
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')  # CORS header
                self.end_headers()
                error_data = json.dumps({"error": "Error fetching USGS data", "message": str(e)})
                self.wfile.write(error_data.encode())
        
        # Handle any other static files
        else:
            try:
                file_path = self.path.strip('/')
                with open(file_path, 'rb') as file:
                    self.send_response(200)
                    if file_path.endswith('.html'):
                        self.send_header('Content-type', 'text/html')
                    elif file_path.endswith('.js'):
                        self.send_header('Content-type', 'application/javascript')
                    elif file_path.endswith('.css'):
                        self.send_header('Content-type', 'text/css')
                    self.end_headers()
                    self.wfile.write(file.read())
            except FileNotFoundError:
                self.send_error(404, "File not found")

def run():
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, USGSProxyHandler)
    print('USGS proxy server running at http://localhost:8000')
    httpd.serve_forever()

if __name__ == '__main__':
    run()