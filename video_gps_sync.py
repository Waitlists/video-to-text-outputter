import sys
import re
import json
import pandas as pd
import asyncio
import threading
import webbrowser
import platform
import os
import shutil

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

import websockets

# ======= YOUR GOOGLE MAPS API KEY HERE =======
GOOGLE_MAPS_API_KEY = "AIzaSyCG6vDTu_3bok8hPkciWYer4uNkfrH1zBE"
# ==============================================

WS_PORT = 8765  # WebSocket server port


class WebSocketBroadcaster:
    def __init__(self):
        self.clients = set()
        self.loop = asyncio.new_event_loop()
        self.server = None
        self.thread = threading.Thread(target=self.start_server, daemon=True)
        self.thread.start()

    async def handler(self, websocket, path):
        self.clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self.clients.remove(websocket)

    def start_server(self):
        asyncio.set_event_loop(self.loop)
        start_server = websockets.serve(self.handler, "localhost", WS_PORT)
        self.server = self.loop.run_until_complete(start_server)
        self.loop.run_forever()

    def broadcast(self, message):
        # Send message (dict) to all clients asynchronously
        if not self.clients:
            return
        data = json.dumps(message)
        asyncio.run_coroutine_threadsafe(self._broadcast(data), self.loop)

    async def _broadcast(self, data):
        to_remove = set()
        for ws in self.clients:
            try:
                await ws.send(data)
            except:
                to_remove.add(ws)
        for ws in to_remove:
            self.clients.remove(ws)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, video_file, gps_file, time_file, broadcaster):
        super().__init__()
        self.setWindowTitle("Video & GPS Trail Sync - Google Maps Live")

        self.broadcaster = broadcaster

        # Load data
        self.gps_df = self.load_gps_data(gps_file)
        self.time_df = self.load_time_data(time_file)

        self.gps_df['time'] = self.gps_df['time'].astype(float)
        self.time_df['time'] = self.time_df['time'].astype(float)

        # UI Elements
        self.video_widget = QVideoWidget()

        self.time_label = QtWidgets.QLabel("Current Time: --:--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.coord_label = QtWidgets.QLabel("Current GPS: --, --")
        self.coord_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Layout
        right_layout = QtWidgets.QVBoxLayout()
        right_layout.addWidget(self.time_label)
        right_layout.addWidget(self.coord_label)
        right_widget = QtWidgets.QWidget()
        right_widget.setLayout(right_layout)

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addWidget(self.video_widget, stretch=3)
        main_layout.addWidget(right_widget, stretch=1)

        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Media player setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.setSource(QUrl.fromLocalFile(video_file))

        # Timer for syncing
        self.timer = QtCore.QTimer()
        self.timer.setInterval(200)  # 5 times per second
        self.timer.timeout.connect(self.sync_data)

        self.player.play()
        self.timer.start()

    def load_gps_data(self, gps_file):
        # Format: "0.0:32°30'43.60\"S115°58'38.47\"E"
        with open(gps_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        data = []
        for line in lines:
            try:
                time_part, gps_part = line.split(':', 1)
                t = float(time_part.strip())
                lat, lon = self.parse_gps_coords(gps_part.strip())
                data.append({'time': t, 'latitude': lat, 'longitude': lon})
            except Exception as e:
                print(f"Error parsing GPS line '{line}': {e}")

        return pd.DataFrame(data)

    def parse_gps_coords(self, gps_str):
        # Convert D°M'S" direction format to decimal degrees
        def dms_to_dd(deg, minute, sec, direction):
            dd = float(deg) + float(minute)/60 + float(sec)/3600
            if direction in ['S', 'W']:
                dd = -dd
            return dd

        # Pattern like: 32°30'43.60"S115°58'38.47"E
        pattern = r"(\d+)°(\d+)'([\d\.]+)\"?([NS])(\d+)°(\d+)'([\d\.]+)\"?([EW])"
        match = re.match(pattern, gps_str)
        if not match:
            raise ValueError(f"Invalid GPS format: {gps_str}")
        lat_deg, lat_min, lat_sec, lat_dir, lon_deg, lon_min, lon_sec, lon_dir = match.groups()

        lat = dms_to_dd(lat_deg, lat_min, lat_sec, lat_dir)
        lon = dms_to_dd(lon_deg, lon_min, lon_sec, lon_dir)
        return lat, lon

    def load_time_data(self, time_file):
        # Format: "0.0: 14:09:21"
        with open(time_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        data = []
        for line in lines:
            try:
                time_part, real_time = line.split(':', 1)
                t = float(time_part.strip())
                real_time = real_time.strip()
                data.append({'time': t, 'real_time': real_time})
            except Exception as e:
                print(f"Error parsing time line '{line}': {e}")

        return pd.DataFrame(data)

    def sync_data(self):
        pos_ms = self.player.position()
        pos_s = pos_ms / 1000.0

        # Find closest GPS point at or before current time
        gps_row = self.gps_df[self.gps_df['time'] <= pos_s].tail(1)
        if gps_row.empty:
            return
        lat = gps_row['latitude'].values[0]
        lon = gps_row['longitude'].values[0]

        # Find closest real time string
        time_row = self.time_df[self.time_df['time'] <= pos_s].tail(1)
        time_str = time_row['real_time'].values[0] if not time_row.empty else "--:--:--"

        # Update UI
        self.time_label.setText(f"Current Time: {time_str}")
        self.coord_label.setText(f"Current GPS: {lat:.6f}, {lon:.6f}")

        # Broadcast to WebSocket clients (browser)
        self.broadcaster.broadcast({'lat': lat, 'lon': lon})


def launch_browser():
    # Write HTML for live Google Maps with WebSocket connection
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Live GPS Map</title>
    <style>
      html, body, #map {{
          height: 100%;
          margin: 0;
          padding: 0;
      }}
    </style>
</head>
<body>
<div id="map"></div>
<script>
  let map;
  let marker;
  let polyline;

  function initMap() {{
    map = new google.maps.Map(document.getElementById('map'), {{
      zoom: 15,
      center: {{lat: 0, lng: 0}},
      mapTypeId: 'roadmap'
    }});
    polyline = new google.maps.Polyline({{
      map: map,
      strokeColor: '#FF0000',
      strokeOpacity: 1.0,
      strokeWeight: 4,
      path: []
    }});
  }}

  const ws = new WebSocket('ws://localhost:{WS_PORT}');
  ws.onmessage = (event) => {{
    const data = JSON.parse(event.data);
    const latlng = new google.maps.LatLng(data.lat, data.lon);
    if (!marker) {{
      marker = new google.maps.Marker({{position: latlng, map: map}});
      map.setCenter(latlng);
    }} else {{
      marker.setPosition(latlng);
    }}
    const path = polyline.getPath();
    path.push(latlng);
    map.panTo(latlng);
  }};

  window.initMap = initMap;
</script>
<script src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_API_KEY}&callback=initMap" async defer></script>
</body>
</html>
"""

    path = os.path.abspath("live_map.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # Try to open in Chrome specifically:
    chrome_path = None

    system = platform.system()
    if system == "Windows":
        # Typical install paths for Chrome on Windows
        paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
        ]
        for p in paths:
            if os.path.exists(p):
                chrome_path = p
                break
    elif system == "Darwin":  # macOS
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif system == "Linux":
        # Assume chrome or google-chrome in PATH
        for cmd in ["google-chrome", "chrome", "chromium-browser", "chromium"]:
            if shutil.which(cmd):
                chrome_path = cmd
                break

    if chrome_path:
        try:
            webbrowser.get(f'"{chrome_path}" %s').open_new_tab("file://" + path)
        except webbrowser.Error:
            # fallback if above fails
            webbrowser.open_new_tab("file://" + path)
    else:
        # Fallback to default browser
        webbrowser.open_new_tab("file://" + path)


def main():
    app = QtWidgets.QApplication(sys.argv)

    video_file, _ = QtWidgets.QFileDialog.getOpenFileName(None, "Select Video File", "", "Videos (*.mp4 *.avi *.mov *.mkv *.ts)")
    gps_file, _ = QtWidgets.QFileDialog.getOpenFileName(None, "Select GPS File", "", "Text Files (*.txt)")
    time_file, _ = QtWidgets.QFileDialog.getOpenFileName(None, "Select Time File", "", "Text Files (*.txt)")

    if not video_file or not gps_file or not time_file:
        QtWidgets.QMessageBox.warning(None, "Missing Input", "You must select all required files.")
        return

    broadcaster = WebSocketBroadcaster()
    window = MainWindow(video_file, gps_file, time_file, broadcaster)
    window.resize(1280, 720)
    window.show()

    # Delay launching browser slightly so WebSocket server is ready
    QtCore.QTimer.singleShot(1000, launch_browser)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
