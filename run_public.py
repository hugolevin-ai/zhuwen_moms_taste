# -*- coding: utf-8 -*-
import subprocess
import time
import os
import sys
import threading
import functools

# Force print statements to flush immediately for real-time log capturing
print = functools.partial(print, flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SERVER_SCRIPT = os.path.join(BASE_DIR, "server.py")

server_proc = None
tunnel_proc = None

def start_server():
    global server_proc
    print("[SYSTEM] Starting local Web Server on port 8080...")
    cmd = [sys.executable, SERVER_SCRIPT]
    server_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5) # Allow server to bind to port

def start_tunnel():
    global tunnel_proc
    print("[SYSTEM] Establishing secure public SSH tunnel via localhost.run...")
    # Use -o StrictHostKeyChecking=no to avoid prompt
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-R", "80:localhost:8080", "nokey@localhost.run"]
    
    tunnel_proc = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        stdin=subprocess.PIPE, 
        text=True
    )
    
    # Read output to capture the public URL
    url = None
    start_time = time.time()
    while time.time() - start_time < 15:
        line = tunnel_proc.stdout.readline()
        if not line:
            # check if process died
            if tunnel_proc.poll() is not None:
                err = tunnel_proc.stderr.read()
                print(f"[ERROR] Tunnel process exited early: {err}")
                break
            time.sleep(0.1)
            continue
            
        line_str = line.strip()
        if "tunneled with tls termination" in line_str or "lhr.life" in line_str:
            # Parse URL
            parts = line_str.split("https://")
            if len(parts) > 1:
                url = "https://" + parts[1].split()[0]
                break
    
    if url:
        print("\n========================================================")
        print("          【 祝文 】 在線公網測試網址已啟用             ")
        print("========================================================")
        print(f"  前台消費者網站: {url}")
        print(f"  後台管理中心  : {url}/admin.html")
        print("========================================================")
        print("  [提示] 您可以將上述網址發送給任何人進行遠端測試。")
        print("  [提示] 本地伺服器與公網通道皆在背景運行。")
        print("  [提示] 按 Ctrl + C 可以安全終止所有連線。")
        print("========================================================\n")
    else:
        print("[ERROR] Failed to retrieve public URL from tunnel. Check your internet connection.")

def main():
    try:
        start_server()
        start_tunnel()
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            # Check if server or tunnel died
            if server_proc and server_proc.poll() is not None:
                print("[SYSTEM] Local server stopped.")
                break
            if tunnel_proc and tunnel_proc.poll() is not None:
                print("[SYSTEM] SSH Tunnel disconnected.")
                break
                
    except KeyboardInterrupt:
        print("\n[SYSTEM] Terminating connection and shutting down...")
    finally:
        # Cleanup
        if tunnel_proc:
            try:
                tunnel_proc.terminate()
                tunnel_proc.wait(timeout=2)
            except:
                pass
        if server_proc:
            try:
                server_proc.terminate()
                server_proc.wait(timeout=2)
            except:
                pass
        print("[SYSTEM] Shutdown completed.")

if __name__ == "__main__":
    main()
