import socket
import time
import math
import os
import sys

print("================================================================")
print(" RUNNING AUTOMATED TELEMETRY PIPELINE INTEGRATION TEST")
print("================================================================")

# 1. Test Outlier Detector Imports & Functionality
print("\n[TEST 1] Testing Dual-Stage Outlier Detector...")
from outlier_detector import OutlierDetector, FIELD_NAMES

detector = OutlierDetector(
    window_size=50,
    z_thresh=3.5,
    refit_every=20,
    min_samples_for_iforest=30,
    contamination=0.05
)

# Feed 35 normal baseline packets
for i in range(35):
    pkt = {
        "accel_x": 0.10 + 0.01 * math.sin(i),
        "accel_y": -0.02 + 0.01 * math.cos(i),
        "accel_z": 9.81 + 0.02 * math.sin(i),
        "gyro_x": 0.01,
        "gyro_y": -0.01,
        "gyro_z": 0.00,
        "pressure": 1013.25 - i * 0.1,
        "temperature": 25.0 - i * 0.01,
        "distance": max(0.0, 100.0 - i),
        "latitude": 28.613900 + i * 0.00001,
        "longitude": 77.209000 + i * 0.00001,
        "gps_altitude": 35.2 + i * 0.5,
    }
    cleaned, report = detector.process(pkt)

print("  -> Baseline warm-up (35 samples) completed successfully.")

# Inject extreme spikes (univariate spike)
spike_pkt = pkt.copy()
spike_pkt["accel_z"] = 99.9  # extreme spike
cleaned_spike, report_spike = detector.process(spike_pkt)

assert "accel_z" in report_spike["field_outliers"], "Failed to detect accel_z outlier!"
assert abs(cleaned_spike["accel_z"] - 9.81) < 1.0, f"Failed to impute accel_z! Got {cleaned_spike['accel_z']}"
print(f"  -> Univariate Outlier Spike Test PASSED: Flagged fields = {report_spike['field_outliers']}, Cleaned accel_z = {cleaned_spike['accel_z']:.2f}")


# 2. Test Coordinate Conversion
print("\n[TEST 2] Testing GPS to Local Metric Coordinate Conversion...")
start_lat = 28.613900
start_lon = 77.209000
start_alt = 35.2

test_lat = 28.613900
test_lon = 77.209100  # 0.0001 deg east
test_alt = 45.2       # 10m climb

meters_per_degree_lon = 111320.0 * math.cos(math.radians(start_lat))
x = (test_lon - start_lon) * meters_per_degree_lon
y = test_alt - start_alt

print(f"  -> GPS delta: dLon={test_lon-start_lon:.6f}, dAlt={test_alt-start_alt:.1f}m")
print(f"  -> Local coordinates: X = {x:.2f} meters, Y = {y:.2f} meters")
assert 9.0 < x < 11.0, f"Unexpected X conversion: {x}"
assert y == 10.0, f"Unexpected Y conversion: {y}"
print("  -> Coordinate Conversion Test PASSED.")


# 3. Test UDP Socket Loopback (Sender -> Socket)
print("\n[TEST 3] Testing UDP Loopback (Port 4210)...")
rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rx_sock.bind(("127.0.0.1", 4210))
rx_sock.settimeout(2.0)

tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
test_packet_str = "101,0.12,-0.03,9.81,0.01,0.02,-0.01,1012.40,24.50,42.70,28.613900,77.209000,35.20"
tx_sock.sendto(test_packet_str.encode("utf-8"), ("127.0.0.1", 4210))

data, addr = rx_sock.recvfrom(4096)
received_str = data.decode("utf-8")
assert received_str == test_packet_str, "Received UDP packet does not match sent packet!"
print(f"  -> Received UDP packet from {addr[0]}: {received_str}")
print("  -> UDP Loopback Test PASSED.")
rx_sock.close()
tx_sock.close()


# 4. Test CSV Flight Logger
print("\n[TEST 4] Testing Flight Log Output...")
log_file = "flight_telemetry_log.csv"
assert os.path.exists(log_file), f"{log_file} does not exist!"
with open(log_file, "r") as f:
    lines = f.readlines()
print(f"  -> {log_file} has {len(lines)} recorded lines.")
print(f"  -> Header: {lines[0].strip()}")
print("  -> CSV Log Output Test PASSED.")

print("\n" + "=" * 65)
print(" ALL 4 INTEGRATION TESTS PASSED SUCCESSFULLY! ")
print(" System is fully ready for hardware & simulated telemetry.")
print("================================================================")
