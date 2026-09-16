from outlier_detector import OutlierDetector, FIELD_NAMES
from collections import deque
import math
import time

# test start

MAX_RANGE_M = 3000.0
MAX_APOGEE_M = 950.0

class MockTelemetryGenerator:
    def __init__(self):
        self.step = 0
        self.flight_number = 1
        self.base_lat = 28.613900
        self.base_lon = 77.209000
        self.base_alt = 150.0

        self.total_flight_time = 15.0
        self.max_steps = int(self.total_flight_time * 10)
        self.max_apogee = MAX_APOGEE_M
        self.max_range = MAX_RANGE_M
        self.apogee_announced = False
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
                self.apogee_announced = False

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

        if tau < 0.70:
            distance = 500.0
        else:
            distance = max(0.0, 500.0 * (1.0 - (tau - 0.70) / 0.30))

        meters_per_deg_lat = 111139.0
        meters_per_deg_lon = 111320.0 * math.cos(math.radians(self.base_lat))

        lat = self.base_lat + (x_dist * 0.7071) / meters_per_deg_lat
        lon = self.base_lon + (x_dist * 0.7071) / meters_per_deg_lon
        alt = abs_alt

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

        if self.step >= self.max_steps:
            self.is_holding = True
            self.hold_until = now + 4.0
        else:
            self.step += 1

        return packet_str


class RobustOutlierDetector(OutlierDetector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.consecutive_flags = {name: 0 for name in FIELD_NAMES}
        self.prev_raw = {name: None for name in FIELD_NAMES}
        self.delta_windows = {name: deque(maxlen=50) for name in FIELD_NAMES}
        self.drift_fields = {"latitude", "longitude", "gps_altitude", "pressure", "temperature", "distance"}

    def _check_field(self, name, value):
        # For drifting kinematic fields, monitor rate of change (delta)
        if name in self.drift_fields:
            if self.prev_raw[name] is None:
                self.prev_raw[name] = value
                self.last_good[name] = value
                return value, False
            
            delta = value - self.last_good[name]
            d_window = self.delta_windows[name]

            if len(d_window) < 5:
                d_window.append(delta)
                self.last_good[name] = value
                self.prev_raw[name] = value
                self.consecutive_flags[name] = 0
                return value, False

            d_scores = self._modified_z_scores(list(d_window) + [delta])
            is_outlier = abs(d_scores[-1]) > self.z_thresh

            # Lockout protection: if flagged 3 times consecutively, accept as true state change
            if is_outlier:
                self.consecutive_flags[name] += 1
                if self.consecutive_flags[name] >= 3:
                    is_outlier = False
                    self.consecutive_flags[name] = 0
            else:
                self.consecutive_flags[name] = 0

            if is_outlier:
                self.stats["field_flags"][name] += 1
                cleaned = self.last_good[name]
            else:
                d_window.append(delta)
                self.last_good[name] = value
                cleaned = value

            self.prev_raw[name] = value
            return cleaned, is_outlier
        else:
            return super()._check_field(name, value)

gen = MockTelemetryGenerator()
det = RobustOutlierDetector(window_size=50, z_thresh=3.5)

print("Running 150 mock steps through RobustOutlierDetector with Euclidean X...")
start_lat = None
start_lon = None
start_alt = None

for step in range(151):
    pkt = gen.next_packet()
    if pkt is None:
        print(f"Step {step}: completed flight, in hold period.")
        break
    parts = pkt.split(",")
    raw = {
        "accel_x": float(parts[1]), "accel_y": float(parts[2]), "accel_z": float(parts[3]),
        "gyro_x": float(parts[4]), "gyro_y": float(parts[5]), "gyro_z": float(parts[6]),
        "pressure": float(parts[7]), "temperature": float(parts[8]),
        "distance": float(parts[9]),
        "latitude": float(parts[10]), "longitude": float(parts[11]), "gps_altitude": float(parts[12])
    }
    if step == 60:
        raw["accel_z"] = 90.0
    if step == 120:
        raw["latitude"] += 0.004500

    cleaned, report = det.process(raw)

    if start_lat is None:
        start_lat = cleaned["latitude"]
        start_lon = cleaned["longitude"]
        start_alt = cleaned["gps_altitude"]

    meters_per_deg_lat = 111139.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(start_lat))
    dx = (cleaned["longitude"] - start_lon) * meters_per_deg_lon
    dy = (cleaned["latitude"] - start_lat) * meters_per_deg_lat
    x = math.hypot(dx, dy)
    y = max(0.0, cleaned["gps_altitude"] - start_alt)

    if report["field_outliers"] or step % 15 == 0 or step >= 148:
        print(f"step {step:03d}: x={x:.1f}m, y={y:.1f}m, raw_alt={raw['gps_altitude']:.1f}, clean_alt={cleaned['gps_altitude']:.1f}, outliers={report['field_outliers']}, multi={report['multivariate_outlier']}")

