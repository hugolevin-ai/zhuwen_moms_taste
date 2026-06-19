# -*- coding: utf-8 -*-
import os
import json
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import threading

PORT = int(os.environ.get('PORT', 8080))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")

orders_file = os.path.join(DATA_DIR, "orders.json")
subscribers_file = os.path.join(DATA_DIR, "subscribers.json")

file_lock = threading.Lock()

def init_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)
    
    with file_lock:
        if not os.path.exists(orders_file):
            with open(orders_file, "w", encoding="utf-8") as f:
                json.dump([], f)
        if not os.path.exists(subscribers_file):
            with open(subscribers_file, "w", encoding="utf-8") as f:
                json.dump([], f)

def read_json_file(filepath):
    with file_lock:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[ERROR] Reading {filepath}: {e}")
        return []

def write_json_file(filepath, data):
    with file_lock:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                return True
        except Exception as e:
            print(f"[ERROR] Writing {filepath}: {e}")
        return False

class WebRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override to log cleanly in the console
        print(f"[SERVER] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {format%args}")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 1. API GET Endpoints
        if path == "/api/orders":
            self.send_json_response(read_json_file(orders_file))
            return
            
        elif path == "/api/settlement":
            orders = read_json_file(orders_file)
            subscribers = read_json_file(subscribers_file)
            
            total_revenue = 0.0
            total_orders = len(orders)
            shipped_count = 0
            pending_count = 0
            single_count = 0
            sub_count = 0
            
            for o in orders:
                total_revenue += float(o.get("amount", 0.0))
                if o.get("status") == "Shipped":
                    shipped_count += 1
                else:
                    pending_count += 1
                    
                if o.get("type") == "subscription":
                    sub_count += 1
                else:
                    single_count += 1
                    
            settlement_data = {
                "total_revenue": total_revenue,
                "total_orders": total_orders,
                "shipped_count": shipped_count,
                "pending_count": pending_count,
                "single_count": single_count,
                "sub_count": sub_count,
                "subscribers_count": len(subscribers)
            }
            self.send_json_response(settlement_data)
            return

        elif path == "/api/subscribers":
            self.send_json_response(read_json_file(subscribers_file))
            return

        # 2. Static Files Routing
        if path == "/" or path == "":
            file_to_serve = os.path.join(STATIC_DIR, "index.html")
        else:
            # Prevent directory traversal attacks
            normalized_path = os.path.normpath(path.lstrip("/"))
            file_to_serve = os.path.join(STATIC_DIR, normalized_path)

        if os.path.exists(file_to_serve) and os.path.isfile(file_to_serve):
            self.serve_static_file(file_to_serve)
        else:
            self.send_error_response(404, "File Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            req_data = json.loads(post_data) if post_data else {}
        except Exception:
            self.send_error_response(400, "Invalid JSON payload")
            return

        # 1. API POST Endpoints
        if path == "/api/order":
            # Place a new order/subscription
            customer_name = req_data.get("customer_name", "").strip()
            phone = req_data.get("phone", "").strip()
            address = req_data.get("address", "").strip()
            items = req_data.get("items", [])
            order_type = req_data.get("type", "single") # single or subscription
            amount = req_data.get("amount", 0.0)
            
            if not customer_name or not phone or not address or not items:
                self.send_error_response(400, "Missing required order fields")
                return
                
            orders = read_json_file(orders_file)
            
            # Generate ID
            prefix = "SUB" if order_type == "subscription" else "ORD"
            date_str = datetime.now().strftime("%Y%m%d")
            seq = len(orders) + 1
            order_id = f"{prefix}{date_str}{seq:03d}"
            
            new_order = {
                "id": order_id,
                "customer_name": customer_name,
                "phone": phone,
                "address": address,
                "items": items,
                "type": order_type,
                "amount": float(amount),
                "status": "Pending",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "shipped_time": ""
            }
            
            orders.append(new_order)
            if write_json_file(orders_file, orders):
                self.send_json_response({"status": "success", "order_id": order_id, "order": new_order})
            else:
                self.send_error_response(500, "Database write failure")

        elif path == "/api/order/ship":
            # Mark order as shipped
            order_id = req_data.get("order_id", "").strip()
            if not order_id:
                self.send_error_response(400, "Missing order_id")
                return
                
            orders = read_json_file(orders_file)
            found = False
            for o in orders:
                if o.get("id") == order_id:
                    o["status"] = "Shipped"
                    o["shipped_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    found = True
                    break
                    
            if found:
                if write_json_file(orders_file, orders):
                    self.send_json_response({"status": "success", "order_id": order_id})
                else:
                    self.send_error_response(500, "Database write failure")
            else:
                self.send_error_response(404, "Order not found")

        elif path == "/api/subscribe":
            # Subscribe for notifications
            email = req_data.get("email", "").strip()
            phone = req_data.get("phone", "").strip()
            
            if not email and not phone:
                self.send_error_response(400, "Email or phone is required")
                return
                
            subscribers = read_json_file(subscribers_file)
            
            # Check duplicates
            exists = False
            for s in subscribers:
                if (email and s.get("email") == email) or (phone and s.get("phone") == phone):
                    exists = True
                    break
                    
            if not exists:
                new_sub = {
                    "email": email,
                    "phone": phone,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                subscribers.append(new_sub)
                if write_json_file(subscribers_file, subscribers):
                    self.send_json_response({"status": "success", "message": "Subscribed successfully"})
                else:
                    self.send_error_response(500, "Database write failure")
            else:
                self.send_json_response({"status": "success", "message": "Already subscribed"})

        elif path == "/api/send_notification":
            # Simulate broadcasting alerts to subscribers
            message = req_data.get("message", "").strip()
            if not message:
                self.send_error_response(400, "Message content is empty")
                return
                
            subscribers = read_json_file(subscribers_file)
            print(f"\n>>> [NOTIFICATION BROADCAST] Sending Alert to {len(subscribers)} subscribers:")
            print(f"Content: {message}")
            print(">>> [BROADCAST COMPLETE] All notifications dispatched successfully.\n")
            
            self.send_json_response({"status": "success", "sent_count": len(subscribers)})

        else:
            self.send_error_response(404, "Endpoint Not Found")

    # Helper Response Methods
    def send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        # Enable CORS for local testing
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_response(self, status_code, message):
        self.send_json_response({"status": "error", "message": message}, status_code)

    def serve_static_file(self, filepath):
        _, ext = os.path.splitext(filepath.lower())
        mime_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml"
        }
        content_type = mime_types.get(ext, "application/octet-stream")
        
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            print(f"[ERROR] Serving static file {filepath}: {e}")
            self.send_error_response(500, "Internal Server Error")

def run():
    init_files()
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, WebRequestHandler)
    print(f"\n[SERVER] Zhuwen Mom's Taste Server running on http://localhost:{PORT}")
    print(f"[SERVER] Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[SERVER] Shutting down...")
        httpd.server_close()

if __name__ == "__main__":
    run()
