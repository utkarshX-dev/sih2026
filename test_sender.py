"""
test_sender.py - VECTOR 155mm Artillery Shell Telemetry Simulator
-----------------------------------------------------------------
Simulates realistic ballistic flight telemetry based on:
"Tenacity - Aim Bot (VECTOR E-Stack)"
- IMU: ICM-20948 (Ogive decoupled ~200 RPM = ~20.9 rad/s roll)
- Barometer: BMP388 (Barometric pressure & temperature lapse)
- GNSS: u-blox NEO-M8N (Ballistic arc with simulated GPS jamming glitches)
- Proximity: AS72651 NIR Multi-Spectral Sensor
"""

import socket
import time
import math

UDP_IP = "127.0.0.1"
UDP_PORT = 4210

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("=" * 60)
print(" VECTOR 155mm SHELL TELEMETRY SIMULATOR")
print(f" Streaming 155mm Ballistic Trajectory to {UDP_IP}:{UDP_PORT}")
print("=" * 60)

# Base Launch Position
base_lat = 28.613900
base_lon = 77.209000
base_alt = 150.0

total_steps = 150  # 15 seconds of flight at 10 Hz
total_flight_time = 15.0  # seconds
max_apogee = 950.0        # peak altitude in meters
max_range = 3000.0        # downrange distance in meters

meters_per_deg_lat = 111139.0
meters_per_deg_lon = 111320.0 * math.cos(math.radians(base_lat))

for i in range(total_steps):
    t = i * 0.1
    tau = t / total_flight_time

    # 1. Parabolic Ballistic Trajectory
    height = 4.0 * max_apogee * tau * (1.0 - tau)
    x_dist = max_range * tau

    # 2. Barometer (BMP388)
    abs_alt = base_alt + height
    pressure = 1013.25 * math.pow((1.0 - 2.25577e-5 * abs_alt), 5.25588)
    temperature = 28.0 - (0.0065 * abs_alt)

    # 3. IMU (ICM-20948)
    roll_rate = 20.94 + 0.4 * math.sin(2.0 * math.pi * t * 0.5)
    pitch_rate = 0.12 * math.cos(t * 0.8)
    yaw_rate = 0.06 * math.sin(t * 0.6)

    accel_x = -1.8 - 0.5 * (1.0 - tau)
    accel_y = 0.20 * math.sin(t * 1.5)
    accel_z = 9.81 + 0.25 * math.cos(t * 1.5)

    # 4. Proximity (AS72651 NIR Sensor)
    if tau < 0.75:
        distance = 500.0
    else:
        distance = max(0.0, 500.0 * (1.0 - (tau - 0.75) / 0.25))

    # 5. GNSS (u-blox NEO-M8N)
    latitude = base_lat + (x_dist * 0.7071) / meters_per_deg_lat
    longitude = base_lon + (x_dist * 0.7071) / meters_per_deg_lon
    gps_altitude = abs_alt

    # 6. Simulated Anti-Jamming & Spikes (Test Outlier Detector)
    if i == 60:
        print("  >>> INJECTING TEST SENSOR SPIKE (Accel Shock: 90 m/s^2) <<<")
        accel_z = 90.0
    elif i == 120:
        print("  >>> INJECTING SIMULATED GPS JAMMING OUTLIER (500m Lat Jump) <<<")
        latitude += 0.004500

    packet = (
        f"{i},"
        f"{accel_x:.2f},{accel_y:.2f},{accel_z:.2f},"
        f"{pitch_rate:.2f},{yaw_rate:.2f},{roll_rate:.2f},"
        f"{pressure:.2f},{temperature:.2f},"
        f"{distance:.2f},"
        f"{latitude:.6f},{longitude:.6f},{gps_altitude:.2f}"
    )

    sock.sendto(packet.encode("utf-8"), (UDP_IP, UDP_PORT))

    if i % 10 == 0:
        print(f"[t={t:.1f}s | Step {i:03d}] Range: {x_dist:.0f}m | Alt: {height:.1f}m | Press: {pressure:.1f}hPa | Roll: {roll_rate:.1f}rad/s")

    time.sleep(0.1)

sock.close()
print("\nVECTOR 155mm Shell Telemetry Simulation Complete.")