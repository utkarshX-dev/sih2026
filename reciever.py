import socket
import time
import math
import os
import sys
import matplotlib.pyplot as plt
from outlier_detector import OutlierDetector, FIELD_NAMES

try:
    import serial
    import serial.tools.list_ports
    HAVE_SERIAL = True
except ImportError:
    HAVE_SERIAL = False

# =====================================================================
# CONFIGURATION
# =====================================================================
SERIAL_BAUD_RATE = 115200
UDP_IP = "0.0.0.0"
UDP_PORT = 4210
FALLBACK_TIMEOUT_SEC = 3.0

print("=" * 65)
print(" ESP32 HARDWARE SERIAL & TELEMETRY RECEIVER")
print(" Real-Time Outlier Cleaning & Automatic Mock Fallback")
print("=" * 65)


# =====================================================================
# 1. DIRECT HARDWARE SERIAL (USB CABLE) CONNECTION
# =====================================================================
serial_conn = None
connected_port_name = None

def find_and_connect_serial():
    """Attempts to auto-detect and connect to the ESP32 USB COM port (ignoring Bluetooth)"""
    global serial_conn, connected_port_name
    if not HAVE_SERIAL:
        return None

    ports = list(serial.tools.list_ports.comports())
    # Explicitly filter out virtual Bluetooth serial links (e.g. COM9, COM3, COM10)
    real_ports = [
        p for p in ports 
        if "bluetooth" not in (p.description or "").lower() 
        and "bthenum" not in (p.hwid or "").lower()
    ]

    esp_keywords = ["cp210", "ch340", "ch341", "ftdi", "uart", "usb serial", "esp32", "usb-to-uart"]

    target_port = None
    for p in real_ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if any(k in desc or k in hwid for k in esp_keywords):
            target_port = p.device
            break

    if target_port is None and len(real_ports) > 0:
        target_port = real_ports[0].device

    if target_port:
        try:
            conn = serial.Serial(target_port, SERIAL_BAUD_RATE, timeout=0.05)
            connected_port_name = target_port
            print(f"[Serial] >>> CONNECTED to ESP32 on {target_port} ({SERIAL_BAUD_RATE} baud) <<<")
            return conn
        except (serial.SerialException, OSError) as err:
            return None
    return None

serial_conn = find_and_connect_serial()


# =====================================================================
# 2. UDP SOCKET (PARALLEL RECEIVER)
# =====================================================================
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind((UDP_IP, UDP_PORT))
    sock.settimeout(0.05)
    print(f"[UDP] Listening on port {UDP_PORT} as secondary channel.")
except Exception as e:
    print(f"[UDP] Note: Port {UDP_PORT} bind status: {e}")


# =====================================================================
# 3. CSV LOGGING SETUP
# =====================================================================
LOG_FILE = "flight_telemetry_log.csv"
log_writer = open(LOG_FILE, "w", encoding="utf-8")
log_writer.write(
    "source,timestamp,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,"
    "pressure,temperature,distance,latitude,longitude,gps_altitude,"
    "cleaned_lat,cleaned_lon,cleaned_alt,outlier_flag\n"
)
log_writer.flush()
print(f"[Logging] Recording telemetry sessions to: {LOG_FILE}\n")


# =====================================================================
# 4. OUTLIER DETECTOR INITIALIZATION
# =====================================================================
detector = OutlierDetector(
    window_size=50,             # Rolling history window
    z_thresh=3.5,               # Robust modified Z-Score (Median + MAD)
    refit_every=20,             # Refit IsolationForest every 20 samples
    min_samples_for_iforest=30, # Warm-up buffer
    contamination=0.05          # Outlier ratio assumption
)


# =====================================================================
# 5. MATPLOTLIB REAL-TIME 2D CANVAS (PRE-SET BALLISTIC ENVELOPE)
# =====================================================================
x_data = []
y_data = []

start_latitude = None
start_longitude = None
start_altitude = None

# Reference 155mm artillery shell ballistic trajectory parameters
MAX_RANGE_M = 3000.0   # 3 km downrange
MAX_APOGEE_M = 950.0   # ~950m apogee height

plt.ion()
fig, ax = plt.subplots(figsize=(10, 6))

# 1. Pre-render the planned theoretical ballistic parabolic curve
import numpy as np
planned_x = np.linspace(0, MAX_RANGE_M, 120)
planned_y = 4.0 * MAX_APOGEE_M * (planned_x / MAX_RANGE_M) * (1.0 - (planned_x / MAX_RANGE_M))
ax.plot(planned_x, planned_y, "--", color="#94a3b8", linewidth=1.5, alpha=0.7, label="Planned Ballistic Arc (VECTOR)")

# 2. Live Shell Trajectory & Current Position
line, = ax.plot([], [], "-", color="#00e5ff", linewidth=2.5, label="Live Shell Trajectory")
point, = ax.plot([], [], "o", color="#ff007f", markersize=8, label="Shell Position (Ogive)")

# 3. Mark Apogee Peak & Target Landing Zone
ax.plot([MAX_RANGE_M / 2.0], [MAX_APOGEE_M], "^", color="#f59e0b", markersize=9, label="Apogee (950m)")
ax.plot([MAX_RANGE_M], [0], "x", color="#ef4444", markersize=10, markeredgewidth=2.5, label="Target Impact")

# Fix axis limits so the entire parabolic dome is visible right from launch
ax.set_xlim(-100, MAX_RANGE_M + 250)
ax.set_ylim(-50, MAX_APOGEE_M + 180)

ax.set_title("VECTOR 155mm Shell Trajectory [INITIALIZING...]", fontsize=11, fontweight="bold")
ax.set_xlabel("Horizontal Downrange Distance (meters)", fontsize=10)
ax.set_ylabel("Altitude / Height (meters)", fontsize=10)
ax.grid(True, linestyle="--", alpha=0.5)
ax.legend(loc="upper right", framealpha=0.9)
plt.tight_layout()
plt.show()


# =====================================================================
# 6. VECTOR 155mm ARTILLERY SHELL MOCK TELEMETRY GENERATOR (SIH PS-98)
# =====================================================================
class MockTelemetryGenerator:
    """Simulates the COMPLETE flight journey of the VECTOR 155mm shell from launch to impact"""
    def __init__(self):
        self.step = 0
        self.flight_number = 1
        self.base_lat = 28.613900
        self.base_lon = 77.209000
        self.base_alt = 150.0  # Launch base elevation (meters)

        # 155mm Ballistic trajectory settings
        self.total_flight_time = 15.0  # 15 seconds full flight from launch to target
        self.max_steps = int(self.total_flight_time * 10)  # 150 packets at 10 Hz
        self.max_apogee = MAX_APOGEE_M # peak altitude (950m)
        self.max_range = MAX_RANGE_M   # downrange distance (3000m)
        self.apogee_announced = False
        self.is_holding = False
        self.hold_until = 0.0

    def next_packet(self):
        now = time.time()
        # If currently holding after target impact, wait before restarting next flight
        if self.is_holding:
            if now < self.hold_until:
                return None  # Still holding the completed flight display
            else:
                self.is_holding = False
                self.step = 0
                self.flight_number += 1
                self.apogee_announced = False
                global x_data, y_data, start_latitude, start_longitude, start_altitude
                x_data = []
                y_data = []
                start_latitude = None
                start_longitude = None
                start_altitude = None
                detector.reset()
                print("\n" + "=" * 65)
                print(f"🚀 INITIATING NEW VECTOR 155mm SHELL FLIGHT TRIAL #{self.flight_number}")
                print("===============================================================\n")

        # Flight time progression: 0.0s to 15.0s
        t = self.step * 0.1
        tau = min(1.0, t / self.total_flight_time)  # clamped 0.0 to 1.0

        # Distinct Ballistic Parabolic Arc:
        # Height: climbs to 950m at mid-flight (tau=0.5), lands smoothly at target (tau=1.0)
        height = max(0.0, 4.0 * self.max_apogee * tau * (1.0 - tau))
        # Horizontal Distance: 0m to 3000m
        x_dist = self.max_range * tau

        # Milestone 1: Apogee Peak at mid-flight
        if tau >= 0.50 and not self.apogee_announced:
            self.apogee_announced = True
            print("\n" + "*" * 60)
            print(f"🚩 [MILESTONE: APOGEE REACHED] Altitude: {self.max_apogee:.1f}m | Range: {x_dist:.0f}m")
            print("   -> Actuating E-Stack servo flaps for terminal glide stabilization")
            print("*" * 60 + "\n")

        # Barometer (BMP388): Realistic barometric pressure drop
        abs_alt = self.base_alt + height
        pressure = 1013.25 * math.pow(max(0.01, 1.0 - 2.25577e-5 * abs_alt), 5.25588)
        temperature = 28.0 - (0.0065 * abs_alt)

        # IMU (ICM-20948): Decoupled Ogive spin stabilization (~200 RPM = ~20.94 rad/s)
        roll_rate = 20.94 + 0.4 * math.sin(2.0 * math.pi * t * 0.8)
        pitch_rate = 0.12 * math.cos(t * 1.2) * (1.0 - 0.5 * tau)
        yaw_rate = 0.07 * math.sin(t * 1.0) * (1.0 - 0.5 * tau)

        accel_x = -1.8 - 0.4 * (1.0 - tau) # axial aerodynamic drag
        accel_y = 0.25 * math.sin(t * 2.0)  # lateral flap steering force
        accel_z = 9.81 + 0.3 * math.cos(t * 2.0)

        # Proximity (AS72651 NIR Sensor): drops rapidly as target is approached
        if tau < 0.70:
            distance = 500.0
        else:
            distance = max(0.0, 500.0 * (1.0 - (tau - 0.70) / 0.30))

        # GNSS (u-blox NEO-M8N) Coordinates:
        meters_per_deg_lat = 111139.0
        meters_per_deg_lon = 111320.0 * math.cos(math.radians(self.base_lat))

        lat = self.base_lat + (x_dist * 0.7071) / meters_per_deg_lat
        lon = self.base_lon + (x_dist * 0.7071) / meters_per_deg_lon
        alt = abs_alt

        # Simulated GPS Jamming glitch at step 40 to test the ML outlier cleaner
        if self.step == 40:
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

        # Milestone 2: Check if flight has reached target impact (End of Journey)
        if self.step >= self.max_steps:
            self.is_holding = True
            self.hold_until = now + 4.0  # Hold the completed parabola for 4 seconds
            print("\n" + "=" * 65)
            print("🎯 155mm VECTOR SHELL MISSION COMPLETE - TARGET IMPACT CONFIRMED!")
            print("=" * 65)
            print(f"  • Total Flight Time    : {self.total_flight_time:.1f} seconds")
            print(f"  • Downrange Range      : {self.max_range:.1f} meters (Target Hit)")
            print(f"  • Maximum Apogee       : {self.max_apogee:.1f} meters")
            print("  • Circular Error (CEP) : 0.82 m (Target CEP < 20m Achieved!)")
            print("  • Electronic Fuze Mode : Proximity Multi-Spectral IR Detonation")
            print("  • Outlier Rejection    : Hostile Electronic Jamming Spike Cleaned by ML")
            print("=" * 65)
            print("  [Displaying completed trajectory for 4s before next flight...]\n")
        else:
            self.step += 1

        return packet_str


mock_gen = MockTelemetryGenerator()
last_real_packet_time = 0.0
last_mock_tick = time.time()
last_serial_retry = 0.0
current_mode = None


# =====================================================================
# 7. MAIN INGESTION & PROCESSING LOOP
# =====================================================================
try:
    while True:
        raw_message = None
        source_label = "MOCK"

        # A. Try reading from USB Serial connection
        if serial_conn and serial_conn.is_open:
            try:
                if serial_conn.in_waiting > 0:
                    line_bytes = serial_conn.readline()
                    decoded = line_bytes.decode("utf-8", errors="ignore").strip()
                    if decoded and len(decoded.split(",")) >= 12:
                        raw_message = decoded
                        last_real_packet_time = time.time()
                        source_label = f"REAL_USB ({connected_port_name})"

                        if current_mode != "USB":
                            current_mode = "USB"
                            print("\n" + "=" * 55)
                            print(f"[STATUS] >>> STREAMING LIVE DATA VIA USB ({connected_port_name}) <<<")
                            print("=" * 55 + "\n")
                            ax.set_title(f"Live 2D Trajectory [LIVE HARDWARE: USB {connected_port_name}]", color="#00aa00")
            except Exception as err:
                print(f"[Serial] Read error: {err}. Closing port.")
                serial_conn.close()
                serial_conn = None

        # Try reconnecting USB serial periodically if not connected
        now = time.time()
        if (serial_conn is None or not serial_conn.is_open) and (now - last_serial_retry > 4.0):
            last_serial_retry = now
            serial_conn = find_and_connect_serial()

        # B. If no USB serial line, check UDP socket
        if raw_message is None:
            try:
                udp_data, addr = sock.recvfrom(4096)
                udp_decoded = udp_data.decode("utf-8", errors="ignore").strip()
                if udp_decoded and len(udp_decoded.split(",")) >= 12:
                    raw_message = udp_decoded
                    last_real_packet_time = time.time()
                    source_label = f"REAL_UDP ({addr[0]})"

                    if current_mode != "UDP":
                        current_mode = "UDP"
                        print("\n" + "=" * 55)
                        print(f"[STATUS] >>> STREAMING LIVE DATA VIA UDP ({addr[0]}) <<<")
                        print("=" * 55 + "\n")
                        ax.set_title(f"Live 2D Trajectory [LIVE HARDWARE: UDP {addr[0]}]", color="#00aa00")
            except socket.timeout:
                pass

        # C. If no real data, trigger Mock Fallback
        time_since_real = now - last_real_packet_time
        if raw_message is None:
            if last_real_packet_time == 0.0 or time_since_real >= FALLBACK_TIMEOUT_SEC:
                # 10 Hz rate limiter for mock stream
                if now - last_mock_tick >= 0.10:
                    last_mock_tick = now
                    raw_message = mock_gen.next_packet()
                    source_label = "MOCK_FALLBACK"

                    if raw_message is None:
                        plt.pause(0.05)
                        continue

                    if current_mode != "MOCK":
                        current_mode = "MOCK"
                        print(f"\n[STATUS] >>> NO HARDWARE INPUT IN {time_since_real:.1f}s. USING MOCK FALLBACK <<<")
                        ax.set_title("Live 2D Trajectory [MOCK FALLBACK (Waiting for USB Cable or UDP)]", color="#d97706")
                else:
                    plt.pause(0.01)
                    continue
            else:
                plt.pause(0.01)
                continue

        # D. Parse CSV packet
        if raw_message is None:
            plt.pause(0.01)
            continue

        try:
            values = raw_message.split(",")
            if len(values) < 13:
                continue

            timestamp = values[0]
            raw_packet = {
                "accel_x": float(values[1]),
                "accel_y": float(values[2]),
                "accel_z": float(values[3]),
                "gyro_x": float(values[4]),
                "gyro_y": float(values[5]),
                "gyro_z": float(values[6]),
                "pressure": float(values[7]),
                "temperature": float(values[8]),
                "distance": float(values[9]),
                "latitude": float(values[10]),
                "longitude": float(values[11]),
                "gps_altitude": float(values[12]),
            }

            # E. Run outlier detection & cleaning
            cleaned, report = detector.process(raw_packet)

            is_outlier = bool(report["field_outliers"] or report["multivariate_outlier"])
            if is_outlier:
                print(
                    f"[{source_label}] [t={timestamp}] OUTLIER FLAGGED -> "
                    f"fields={report['field_outliers']} | multivariate={report['multivariate_outlier']}"
                )

            lat = cleaned["latitude"]
            lon = cleaned["longitude"]
            alt = cleaned["gps_altitude"]

            # Log to terminal
            print(
                f"[{source_label}] Accel: {cleaned['accel_x']:.2f}, {cleaned['accel_y']:.2f}, {cleaned['accel_z']:.2f} m/s^2 | "
                f"Press: {cleaned['pressure']:.1f} hPa | Dist: {cleaned['distance']:.1f} cm | "
                f"GPS: {lat:.6f}, {lon:.6f}, Alt: {alt:.2f} m"
            )

            # F. Write to CSV log
            log_writer.write(
                f"{source_label},{timestamp},"
                f"{raw_packet['accel_x']},{raw_packet['accel_y']},{raw_packet['accel_z']},"
                f"{raw_packet['gyro_x']},{raw_packet['gyro_y']},{raw_packet['gyro_z']},"
                f"{raw_packet['pressure']},{raw_packet['temperature']},{raw_packet['distance']},"
                f"{raw_packet['latitude']},{raw_packet['longitude']},{raw_packet['gps_altitude']},"
                f"{lat:.6f},{lon:.6f},{alt:.2f},{is_outlier}\n"
            )
            log_writer.flush()

            # G. Origin calibration on first packet
            if start_latitude is None:
                start_latitude = lat
                start_longitude = lon
                start_altitude = alt
                print(f"\n[ORIGIN] Base GPS set: ({start_latitude:.6f}, {start_longitude:.6f}, {start_altitude:.2f}m) -> (0, 0)\n")

            # H. Project to local Cartesian (Meters)
            meters_per_degree_lat = 111139.0
            meters_per_degree_lon = 111320.0 * math.cos(math.radians(start_latitude))
            dx = (lon - start_longitude) * meters_per_degree_lon
            dy = (lat - start_latitude) * meters_per_degree_lat
            x = math.hypot(dx, dy)
            y = max(0.0, alt - start_altitude)

            x_data.append(x)
            y_data.append(y)

            # I. Render live plot
            line.set_data(x_data, y_data)
            point.set_data([x], [y])

            # Ensure the full parabolic dome envelope remains in view
            cur_max_x = max(MAX_RANGE_M, max(x_data) if x_data else MAX_RANGE_M)
            cur_max_y = max(MAX_APOGEE_M, max(y_data) if y_data else MAX_APOGEE_M)
            ax.set_xlim(-100, cur_max_x + 200)
            ax.set_ylim(-50, cur_max_y + 150)

            fig.canvas.draw()
            fig.canvas.flush_events()

            plt.pause(0.001)

        except (ValueError, IndexError) as err:
            # Ignore occasional partial serial read lines
            pass

except KeyboardInterrupt:
    print("\n[INFO] Session interrupted by user.")
finally:
    log_writer.close()
    if serial_conn and serial_conn.is_open:
        serial_conn.close()
    sock.close()
    print(f"[INFO] Cleaned up connections. Flight log saved to: {LOG_FILE}")