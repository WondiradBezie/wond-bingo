# install.py
import subprocess
import sys

packages = [
    "Werkzeug==2.3.7",
    "Flask==2.3.3",
    "python-socketio==5.9.0",
    "eventlet==0.33.3",
    "Flask-SocketIO==5.3.4",
    "Flask-SQLAlchemy==3.1.1",
    "Flask-Login==0.6.2",
    "Flask-CORS==4.0.0",
    "gunicorn==21.2.0"
]

print("Installing packages...")
for package in packages:
    print(f"Installing {package}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

print("\n✅ All packages installed!")
print("Testing eventlet...")
subprocess.check_call([sys.executable, "-c", "import eventlet; print('✅ Eventlet works!')"])