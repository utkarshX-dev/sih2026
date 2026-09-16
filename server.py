"""
server.py - VECTOR 155mm Shell Web Ground Control Station (GCS)
-----------------------------------------------------------------
Hosts a high-performance HTTP + Server-Sent Events (SSE) server
connecting the live ESP32 / Mock Telemetry pipeline to the web dashboard.
"""

import http.server
import socketserver
import threading
import json
import time
import math
import os
import socket

from outlier_detector import OutlierDetector

try:
    import serial
    import serial.tools.list_ports
    HAVE_SERIAL = True
except ImportError:
    HAVE_SERIAL = False

PORT = 5000
UDP_PORT = 4210
SERIAL_BAUD_RATE = 115200

# =====================================================================
# GLOBAL TELEMETRY STATE
# =====================================================================
telemetry_lock = threading.Lock()
clients = []

current_telemetry = {
    "source": "INITIALIZING",
    "timestamp": "0",
    "flight_time": 0.0,
    "x": 0.0,
    "y": 0.0,
    "velocity": 0.0,
    "accel_x": 0.0,
    "accel_y": 0.0,
    "accel_z": 9.81,
    "gyro_x": 0.0,
    "gyro_y": 0.0,
    "gyro_z": 20.94,
    "roll_rpm": 200.0,
    "pressure": 1013.25,
    "temperature": 28.0,
    "distance": 500.0,
    "latitude": 28.613900,
    "longitude": 77.209000,
    "altitude": 150.0,
    "cleaned_lat": 28.613900,
    "cleaned_lon": 77.209000,
    "cleaned_alt": 150.0,
    "is_outlier": False,
    "field_outliers": [],
    "multivariate_outlier": False,
    "phase": "LAUNCH_STANDBY",
    "trajectory": [],
    "max_range": 3000.0,
    "max_apogee": 950.0,
    "trial_count": 1,
    "hold_countdown": 0.0,
}

# =====================================================================
# OUTLIER DETECTOR
# =====================================================================
detector = OutlierDetector(
    window_size=50,
    z_thresh=3.5,
    refit_every=20,
    min_samples_for_iforest=30,
    contamination=0.05
)

# =====================================================================
# VECTOR 155mm SHELL MOCK GENERATOR (SIH PS-98)
# =====================================================================
class VectorShellMockGenerator:
    def __init__(self):
        self.step = 0
        self.flight_number = 1
        self.base_lat = 28.613900
        self.base_lon = 77.209000
        self.base_alt = 150.0
        self.total_flight_time = 15.0  # seconds
        self.max_steps = int(self.total_flight_time * 10) # 150 steps
        self.max_apogee = 950.0
        self.max_range = 3000.0
        self.is_holding = False
        self.hold_until = 0.0

    def next_packet(self):
        now = time.time()
        if self.is_holding:
            if now < self.hold_until:
                return None
            else:
                self.is_holding = False
                self.step = 0
                self.flight_number += 1
                detector.reset()
                with telemetry_lock:
                    current_telemetry["trajectory"] = []
                    current_telemetry["trial_count"] = self.flight_number
                    current_telemetry["phase"] = "BALLISTIC_ASCENT"
                    current_telemetry["hold_countdown"] = 0.0

        t = self.step * 0.1
        tau = min(1.0, t / self.total_flight_time)

        height = max(0.0, 4.0 * self.max_apogee * tau * (1.0 - tau))
        x_dist = self.max_range * tau

        abs_alt = self.base_alt + height
        pressure = 1013.25 * math.pow(max(0.01, 1.0 - 2.25577e-5 * abs_alt), 5.25588)
        temperature = 28.0 - (0.0065 * abs_alt)

        roll_rate = 20.94 + 0.4 * math.sin(2.0 * math.pi * t * 0.8)
        pitch_rate = 0.12 * math.cos(t * 1.2) * (1.0 - 0.5 * tau)
        yaw_rate = 0.07 * math.sin(t * 1.0) * (1.0 - 0.5 * tau)

        accel_x = -1.8 - 0.4 * (1.0 - tau)
        accel_y = 0.25 * math.sin(t * 2.0)
        accel_z = 9.81 + 0.3 * math.cos(t * 2.0)

        distance = 500.0 if tau < 0.70 else max(0.0, 500.0 * (1.0 - (tau - 0.70) / 0.30))

        meters_per_deg_lat = 111139.0
        meters_per_deg_lon = 111320.0 * math.cos(math.radians(self.base_lat))

        lat = self.base_lat + (x_dist * 0.7071) / meters_per_deg_lat
        lon = self.base_lon + (x_dist * 0.7071) / meters_per_deg_lon
        alt = abs_alt

        # Simulated electronic warfare GPS jamming glitch
        if self.step == 45:
            lat += 0.003500
            alt += 120.0

        packet_str = (
            f"{self.step},"
            f"{accel_x:.2f},{accel_y:.2f},{accel_z:.2f},"
            f"{pitch_rate:.2f},{yaw_rate:.2f},{roll_rate:.2f},"
            f"{pressure:.2f},{temperature:.2f},"
            f"{distance:.2f},"
            f"{lat:.6f},{lon:.6f},{alt:.2f}"
        )

        if self.step >= self.max_steps:
            self.is_holding = True
            self.hold_until = now + 4.5
        else:
            self.step += 1

        return packet_str

mock_gen = VectorShellMockGenerator()

# =====================================================================
# BACKGROUND TELEMETRY INGESTION THREAD
# =====================================================================
def telemetry_worker():
    global current_telemetry
    last_real_packet_time = 0.0
    last_mock_tick = time.time()
    start_latitude = None
    start_longitude = None
    start_altitude = None

    # Setup UDP socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        udp_sock.bind(("0.0.0.0", UDP_PORT))
        udp_sock.settimeout(0.05)
    except Exception as e:
        print(f"[UDP] Bind note: {e}")

    # Setup Serial
    ser_conn = None
    last_serial_scan = 0.0

    while True:
        raw_msg = None
        source_label = "MOCK"
        now = time.time()

        # 1. Try reading from USB Serial
        if HAVE_SERIAL:
            if ser_conn and ser_conn.is_open:
                try:
                    if ser_conn.in_waiting > 0:
                        line_bytes = ser_conn.readline()
                        decoded = line_bytes.decode("utf-8", errors="ignore").strip()
                        if decoded and len(decoded.split(",")) >= 12:
                            raw_msg = decoded
                            last_real_packet_time = now
                            source_label = f"REAL_USB ({ser_conn.port})"
                except Exception:
                    try:
                        ser_conn.close()
                    except Exception:
                        pass
                    ser_conn = None

            # Periodic scan for USB ESP32
            if (ser_conn is None or not ser_conn.is_open) and (now - last_serial_scan > 4.0):
                last_serial_scan = now
                try:
                    ports = list(serial.tools.list_ports.comports())
                    real_ports = [p for p in ports if "bluetooth" not in (p.description or "").lower() and "bthenum" not in (p.hwid or "").lower()]
                    esp_keys = ["cp210", "ch340", "ch341", "ftdi", "uart", "usb serial", "esp32"]
                    target = None
                    for p in real_ports:
                        desc = (p.description or "").lower()
                        if any(k in desc for k in esp_keys):
                            target = p.device
                            break
                    if target is None and len(real_ports) > 0:
                        target = real_ports[0].device
                    if target:
                        ser_conn = serial.Serial(target, SERIAL_BAUD_RATE, timeout=0.05)
                except Exception:
                    ser_conn = None

        # 2. Try UDP if no serial packet
        if raw_msg is None:
            try:
                udp_bytes, addr = udp_sock.recvfrom(4096)
                udp_decoded = udp_bytes.decode("utf-8", errors="ignore").strip()
                if udp_decoded and len(udp_decoded.split(",")) >= 12:
                    raw_msg = udp_decoded
                    last_real_packet_time = now
                    source_label = f"REAL_UDP ({addr[0]})"
            except socket.timeout:
                pass

        # 3. Fallback to Mock Generator if no real hardware input
        time_since_real = now - last_real_packet_time
        if raw_msg is None:
            if last_real_packet_time == 0.0 or time_since_real >= 3.0:
                if mock_gen.is_holding:
                    rem = max(0.0, mock_gen.hold_until - now)
                    with telemetry_lock:
                        current_telemetry["phase"] = "TARGET_IMPACT"
                        current_telemetry["hold_countdown"] = round(rem, 1)
                    time.sleep(0.08)
                    mock_gen.next_packet()  # Triggers step 0 reset once timer expires
                    continue

                if now - last_mock_tick >= 0.10:
                    last_mock_tick = now
                    mock_packet = mock_gen.next_packet()
                    if mock_packet is not None:
                        raw_msg = mock_packet
                        source_label = "MOCK_VECTOR_155MM"
                else:
                    time.sleep(0.01)
                    continue
            else:
                time.sleep(0.01)
                continue

        if raw_msg is None:
            time.sleep(0.01)
            continue

        # Parse CSV packet
        try:
            parts = raw_msg.split(",")
            if len(parts) < 13:
                continue

            timestamp = parts[0]
            raw_pkt = {
                "accel_x": float(parts[1]),
                "accel_y": float(parts[2]),
                "accel_z": float(parts[3]),
                "gyro_x": float(parts[4]),
                "gyro_y": float(parts[5]),
                "gyro_z": float(parts[6]),
                "pressure": float(parts[7]),
                "temperature": float(parts[8]),
                "distance": float(parts[9]),
                "latitude": float(parts[10]),
                "longitude": float(parts[11]),
                "gps_altitude": float(parts[12]),
            }

            cleaned, report = detector.process(raw_pkt)
            is_outlier = bool(report["field_outliers"] or report["multivariate_outlier"])

            lat = cleaned["latitude"]
            lon = cleaned["longitude"]
            alt = cleaned["gps_altitude"]

            if start_latitude is None or timestamp == "0":
                start_latitude = lat
                start_longitude = lon
                start_altitude = alt

            meters_per_degree_lat = 111139.0
            meters_per_degree_lon = 111320.0 * math.cos(math.radians(start_latitude))
            dx = (lon - start_longitude) * meters_per_degree_lon
            dy = (lat - start_latitude) * meters_per_degree_lat
            x = math.hypot(dx, dy)
            y = max(0.0, alt - start_altitude)

            # Compute mission phase & velocity
            tau = x / 3000.0 if x <= 3000.0 else 1.0
            if y >= 945.0:
                phase = "APOGEE_GLIDE"
            elif tau >= 0.98 or (tau >= 0.92 and y <= 5.0):
                phase = "TARGET_IMPACT"
            elif tau >= 0.50:
                phase = "TERMINAL_DESCENT"
            else:
                phase = "BALLISTIC_ASCENT"

            # Roll rate in RPM: 1 rad/s = 9.549 RPM
            roll_rpm = abs(cleaned["gyro_z"]) * 9.5493

            with telemetry_lock:
                current_telemetry["source"] = source_label
                current_telemetry["timestamp"] = timestamp
                current_telemetry["x"] = round(x, 1)
                current_telemetry["y"] = round(y, 1)
                current_telemetry["accel_x"] = round(cleaned["accel_x"], 2)
                current_telemetry["accel_y"] = round(cleaned["accel_y"], 2)
                current_telemetry["accel_z"] = round(cleaned["accel_z"], 2)
                current_telemetry["gyro_x"] = round(cleaned["gyro_x"], 2)
                current_telemetry["gyro_y"] = round(cleaned["gyro_y"], 2)
                current_telemetry["gyro_z"] = round(cleaned["gyro_z"], 2)
                current_telemetry["roll_rpm"] = round(roll_rpm, 1)
                current_telemetry["pressure"] = round(cleaned["pressure"], 1)
                current_telemetry["temperature"] = round(cleaned["temperature"], 1)
                current_telemetry["distance"] = round(cleaned["distance"], 1)
                current_telemetry["latitude"] = round(raw_pkt["latitude"], 6)
                current_telemetry["longitude"] = round(raw_pkt["longitude"], 6)
                current_telemetry["altitude"] = round(raw_pkt["gps_altitude"], 1)
                current_telemetry["cleaned_lat"] = round(lat, 6)
                current_telemetry["cleaned_lon"] = round(lon, 6)
                current_telemetry["cleaned_alt"] = round(alt, 1)
                current_telemetry["is_outlier"] = bool(is_outlier)
                current_telemetry["field_outliers"] = [str(f) for f in report["field_outliers"]]
                current_telemetry["multivariate_outlier"] = bool(report["multivariate_outlier"])
                current_telemetry["phase"] = str(phase)

                # Append to trajectory history (subsample if needed)
                current_telemetry["trajectory"].append({"x": float(round(x, 1)), "y": float(round(y, 1))})
                if len(current_telemetry["trajectory"]) > 600:
                    current_telemetry["trajectory"] = current_telemetry["trajectory"][-600:]

        except Exception as err:
            pass

# Start ingestion thread
ingest_thread = threading.Thread(target=telemetry_worker, daemon=True)
ingest_thread.start()

# =====================================================================
# HTTP REQUEST HANDLER WITH SSE & REST APIS
# =====================================================================
class WebGCSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(os.path.dirname(__file__), "web"), **kwargs)

    def do_GET(self):
        if self.path == "/api/telemetry" or self.path == "/events":
            # Server-Sent Events stream
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    with telemetry_lock:
                        payload = json.dumps(current_telemetry, default=str)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.08) # ~12 Hz streaming
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        elif self.path == "/api/state":
            # Single JSON snapshot
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with telemetry_lock:
                self.wfile.write(json.dumps(current_telemetry, default=str).encode("utf-8"))
            return

        elif self.path == "/api/reset":
            with telemetry_lock:
                current_telemetry["trajectory"] = []
                current_telemetry["phase"] = "BALLISTIC_ASCENT"
                current_telemetry["hold_countdown"] = 0.0
                mock_gen.step = 0
                mock_gen.is_holding = False
                mock_gen.flight_number += 1
                detector.reset()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"reset"}')
            return

        # Serve static HTML/CSS/JS files from ./web
        return super().do_GET()

    def log_message(self, format, *args):
        # Silence standard HTTP access log noise
        return

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), WebGCSHandler) as httpd:
        print("=" * 65)
        print(" [ONLINE] VECTOR 155mm SHELL WEB GROUND CONTROL STATION")
        print("=" * 65)
        print(f" [URL] Open in browser: http://localhost:{PORT}")
        print(f"       LAN Access:       http://192.168.1.21:{PORT}")
        print("=" * 65 + "\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Server] Shutting down.")

if __name__ == "__main__":
    run_server()
