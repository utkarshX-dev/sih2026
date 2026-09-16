"""
outlier_detector.py

Dual-Stage Outlier Detection & Anti-Jamming Filter Engine
Designed for the "VECTOR" 155mm Precision Guided Artillery Shell (SIH Problem Statement 98)

Sensors:
  - IMU (ICM-20948): Accelerometer (Ax, Ay, Az), Gyroscope (Gx, Gy, Gz)
  - Barometer (BMP388): Barometric Pressure, Ambient Temperature
  - Proximity Fuze (AS72651 NIR Multi-Spectral): Target Distance
  - GNSS (u-blox NEO-M8N): Latitude, Longitude, GPS Altitude

Architecture:
  Layer 1: Robust Kinematic Delta & Modified Z-Score Filter (Rolling Median + MAD)
           - Stationary fields (IMU) are checked against rolling scale with noise floor.
           - Kinematic drift fields (GNSS, Barometer, Fuze) are checked on step-to-step deltas
             to handle continuous parabolic flight without false descent tripping.
           - Physical maximum rate bounds guard against electronic warfare (EW) GPS jamming spikes.
           - Outliers are smoothly cleaned via velocity extrapolation rather than dropping packets.
  Layer 2: Periodic Multivariate IsolationForest ML Check
           - Evaluates joint sensor correlation (e.g. cross-axis anomalies).
"""

from collections import deque
import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    HAVE_SKLEARN = True
except ImportError:
    HAVE_SKLEARN = False


FIELD_NAMES = [
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "pressure", "temperature",
    "distance",
    "latitude", "longitude", "gps_altitude",
]

STATIONARY_FIELDS = [
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
]

DRIFT_FIELDS = [
    "latitude", "longitude", "gps_altitude",
    "pressure", "temperature", "distance",
]


class OutlierDetector:
    def __init__(
        self,
        window_size=50,
        z_thresh=3.5,
        refit_every=20,
        min_samples_for_iforest=30,
        contamination=0.05,
    ):
        self.window_size = window_size
        self.z_thresh = z_thresh
        self.refit_every = refit_every
        self.min_samples_for_iforest = min_samples_for_iforest
        self.contamination = contamination

        # Noise scale floors (prevents division by tiny MADs during steady flight)
        self.mad_floor = {
            "accel_x": 0.8,
            "accel_y": 0.8,
            "accel_z": 0.8,
            "gyro_x": 0.5,
            "gyro_y": 0.5,
            "gyro_z": 1.0,
            "gps_altitude": 5.0,
            "latitude": 0.0002,
            "longitude": 0.0002,
            "pressure": 2.0,
            "temperature": 0.5,
            "distance": 20.0,
        }

        # Maximum plausible physical change per 100ms packet (based on 155mm ballistics)
        self.max_physical_delta = {
            "gps_altitude": 35.0,    # 350 m/s max vertical rate
            "latitude": 0.0010,       # ~111m per 100ms
            "longitude": 0.0010,      # ~111m per 100ms
            "pressure": 15.0,         # 15 hPa per 100ms
            "temperature": 3.0,       # 3 deg C per 100ms
            "distance": 80.0,         # 80 cm per 100ms
        }

        self.reset()

    def reset(self):
        """Resets all history windows and state for a fresh flight run."""
        self.windows = {name: deque(maxlen=self.window_size) for name in FIELD_NAMES}
        self.delta_windows = {name: deque(maxlen=self.window_size) for name in DRIFT_FIELDS}
        self.last_good = {name: None for name in FIELD_NAMES}
        self.last_delta = {name: 0.0 for name in DRIFT_FIELDS}
        self.streak = {name: 0 for name in FIELD_NAMES}

        self.iforest = None
        self.samples_since_refit = 0
        self.multivariate_window = deque(maxlen=self.window_size)

        self.stats = {
            "total": 0,
            "field_flags": {name: 0 for name in FIELD_NAMES},
            "multivariate_flags": 0,
        }

    # ---------- Multivariate check (IsolationForest) ----------

    def _check_multivariate(self, feature_vector):
        if not HAVE_SKLEARN:
            return False

        self.multivariate_window.append(feature_vector)
        self.samples_since_refit += 1

        if len(self.multivariate_window) < self.min_samples_for_iforest:
            return False

        if self.iforest is None or self.samples_since_refit >= self.refit_every:
            try:
                X = np.array(self.multivariate_window)
                self.iforest = IsolationForest(
                    n_estimators=50,
                    contamination=self.contamination,
                    random_state=42,
                )
                self.iforest.fit(X)
                self.samples_since_refit = 0
            except Exception:
                return False

        try:
            pred = self.iforest.predict([feature_vector])[0]
            flagged = (pred == -1)
            if flagged:
                self.stats["multivariate_flags"] += 1
            return flagged
        except Exception:
            return False

    # ---------- Public processing API ----------

    def process(self, packet: dict):
        """
        Process an incoming sensor packet.
        packet: dict mapping FIELD_NAMES to float values

        Returns: (cleaned_packet: dict, report: dict)
        """
        self.stats["total"] += 1
        cleaned = {}
        field_outliers = []

        # 1. Stationary Sensor Fields (IMU)
        for name in STATIONARY_FIELDS:
            val = float(packet[name])
            win = self.windows[name]

            if len(win) < 5:
                win.append(val)
                self.last_good[name] = val
                cleaned[name] = val
                continue

            med = float(np.median(win))
            mad = float(np.median(np.abs(np.array(win) - med)))
            mad = max(self.mad_floor[name], mad)
            z_score = 0.6745 * abs(val - med) / mad

            if z_score > self.z_thresh:
                self.streak[name] += 1
                if self.streak[name] > 4:
                    # Persistent real change: accept new baseline
                    win.append(val)
                    self.last_good[name] = val
                    cleaned[name] = val
                    self.streak[name] = 0
                else:
                    field_outliers.append(name)
                    self.stats["field_flags"][name] += 1
                    cleaned[name] = self.last_good[name]
            else:
                self.streak[name] = 0
                win.append(val)
                self.last_good[name] = val
                cleaned[name] = val

        # 2. Kinematic Drift Fields (GNSS, Barometer, Proximity)
        for name in DRIFT_FIELDS:
            val = float(packet[name])
            if self.last_good[name] is None:
                self.last_good[name] = val
                self.windows[name].append(val)
                cleaned[name] = val
                continue

            delta = val - self.last_good[name]
            d_win = self.delta_windows[name]

            is_outlier = False
            # Check A: Exceeds physical ballistic rate of change
            if abs(delta) > self.max_physical_delta[name]:
                is_outlier = True
            # Check B: Delta modified Z-score against recent flight dynamics
            elif len(d_win) >= 5:
                med_d = float(np.median(d_win))
                mad_d = float(np.median(np.abs(np.array(d_win) - med_d)))
                mad_d = max(self.mad_floor[name], mad_d)
                z_delta = 0.6745 * abs(delta - med_d) / mad_d
                if z_delta > self.z_thresh:
                    is_outlier = True

            if is_outlier:
                self.streak[name] += 1
                if self.streak[name] > 4:
                    # Sensor state persistent update
                    d_win.append(delta)
                    self.last_good[name] = val
                    cleaned[name] = val
                    self.streak[name] = 0
                else:
                    field_outliers.append(name)
                    self.stats["field_flags"][name] += 1
                    # Smooth velocity extrapolation
                    cleaned[name] = self.last_good[name] + self.last_delta[name]
            else:
                self.streak[name] = 0
                d_win.append(delta)
                self.last_delta[name] = delta
                self.last_good[name] = val
                self.windows[name].append(val)
                cleaned[name] = val

        # 3. Multivariate Feature Vector (Stationary values + Drift deltas)
        feature_vector = [
            cleaned[name] if name in STATIONARY_FIELDS else self.last_delta[name]
            for name in FIELD_NAMES
        ]
        multivariate_outlier = self._check_multivariate(feature_vector)

        report = {
            "field_outliers": field_outliers,
            "multivariate_outlier": multivariate_outlier,
        }
        return cleaned, report

    def summary(self):
        return self.stats