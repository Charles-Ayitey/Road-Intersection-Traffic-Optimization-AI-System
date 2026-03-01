import subprocess
import time
import os
import sys
import requests

def launch():
    print("🚀 Starting Smart Traffic Junction System...")
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)
    python_exe = sys.executable

    # 1. Start the API
    print("Step 1: Launching Data Bus (API)...")
    api_proc = subprocess.Popen([python_exe, "api/main.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    
    # CLEAR OLD DATA
    try:
        requests.get("http://localhost:8000/reset")
        print("✅ System Memory Cleared.")
    except:
        pass
    
    # 2. Start the Vision Pipeline
    print("Step 2: Launching Vision Detector (YOLOv8)...")
    vision_proc = subprocess.Popen([python_exe, "vision/detector.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 3. Start the Dashboard
    print("Step 3: Launching AI Dashboard...")
    dashboard_cmd = [python_exe, "-m", "streamlit", "run", "dashboard/app.py", "--server.headless", "true"]
    dashboard_proc = subprocess.Popen(dashboard_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("✅ Dashboard ready at http://127.0.0.1:8501")
    
    # 4. Start the RL Controller
    print("Step 4: Launching AI Controller...")
    try:
        subprocess.run([python_exe, "ai_agent/live_controller.py"])
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        api_proc.terminate()
        vision_proc.terminate()
        dashboard_proc.terminate()
        print("Done.")

if __name__ == "__main__":
    launch()
