# 🎯 VECTOR: 155mm Precision Guided Artillery Shell & Smart Fuze E-Stack
### Smart India Hackathon 2026 | Problem Statement ID: 98 | Team Tenacity (R15-230)
**Theme**: Smart Vehicles &bull; **Category**: Hardware &bull; **Presentation Guide**: [**👉 View 3-Speaker Speech & Presentation Guide (EXPLANATION_README.md)**](file:///c:/Users/UTKARSH%20BHANDARI/OneDrive/Desktop/sih/EXPLANATION_README.md)

---

## 📌 Project Overview

**VECTOR** (*Velocity, Estimation, Correction & Trajectory Ogive Retrofit*) is a low SWaP-C (Size, Weight, Power, and Cost) smart electronic fuze and precision guidance retrofit engineered for standard 155mm artillery shells (e.g. ATAGS, Dhanush, K9 Vajra, Bofors, M777). 

It replaces standard mechanical nose fuzes with an advanced decoupled electronic stack featuring:
1. **Decoupled Ogive Mechanism**: Uses precision bearings to decouple the front nose from the 15,000 RPM rifled shell body down to **< 200 RPM**, enabling aerodynamic canard steering.
2. **Battery-Less Electromagnetic Induction Generator**: Harvests power from the relative spin of Neodymium N52 magnets against stationary copper coils, offering **infinite shelf life** with zero chemical hazards.
3. **Dual-Stage Outlier & Anti-Jamming ML Filter**: Combines a rolling kinematic Modified Z-Score (MAD, $N=50$) with a Multivariate Isolation Forest to neutralize enemy Electronic Warfare (EW) and GPS jamming spikes.
4. **Multi-Spectral NIR Smart Fuze (AS72651)**: Differentiates armored military targets from foliage, birds, and decoys for precision airburst proximity detonation.
5. **Live Web Ground Control Station (GCS) & ESP32 Telemetry**: High-speed real-time ballistic trajectory plotting and sensor instrument gauges via direct USB serial and Server-Sent Events (SSE).

---

## 📁 Repository Structure

```text
├── FLOWCHART.md            # 📐 Complete engineering flowcharts (Mermaid diagrams)
├── EXPLANATION_README.md   # 🗣️ 3-Speaker presentation script, slide walkthrough & Q&A defense
├── Tenacity - Aim Bot.pptx # 📊 Official Smart India Hackathon 2026 presentation deck
├── server.py               # 🌐 Web Ground Control Station HTTP + SSE live telemetry server
├── web/                    # 🛡️ Defense GCS Tactical Web UI (MIL-STD-1553B theme)
│   ├── index.html          # Dynamic 2D trajectory viewport, sensor gauges & anti-jamming monitor
│   ├── flowchart.html      # 📊 Interactive visual flowchart viewer (Mermaid.js)
│   ├── style.css           # Tactical military HUD styling (Aviation Amber, Radar Green, Blue)
│   └── app.js              # Real-time trajectory plotting & SSE telemetry intake
├── outlier_detector.py     # 🛡️ Dual-stage ML outlier engine (Kinematic MAD + Isolation Forest)
├── esp32_firmware.ino      # 🔌 Arduino C++ sketch for ESP32 flight computer (Direct USB Serial)
├── reciever.py             # 📈 Standalone Matplotlib desktop trajectory visualizer
├── test_sender.py          # 🧪 Telemetry simulator for standalone testing
├── vector_155mm_flight_data.csv # 📊 Real-world recorded 155mm flight trajectory dataset
├── flight_telemetry_log.csv# 💾 Auto-logged mission telemetry recording
└── requirements.txt        # 📦 Python package dependencies
```

---

## 🚀 Quick Start: Running the Systems

### Option A: Launch the Web Ground Control Station (Recommended for Demos)
```powershell
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Start the high-performance GCS server
python server.py
```
Open your web browser to **`http://localhost:5000`** to view the live ballistic trajectory viewport, decoupled 200 RPM spin gauges, and the anti-jamming filter monitor!

### Option B: Launch the Desktop Matplotlib Visualizer
```powershell
python reciever.py
```

## 🛠️ Step 1: Python Environment Setup

### 1. Open Terminal and Navigate to Project Directory
```powershell
cd "c:\Users\UTKARSH BHANDARI\OneDrive\Desktop\sih"
```

### 2. Activate Your Virtual Environment
* **PowerShell**:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
* **Git Bash**:
  ```bash
  source .venv/Scripts/activate
  ```
* **Command Prompt (`cmd`)**:
  ```cmd
  .\.venv\Scripts\activate.bat
  ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🔌 Step 2: Upload Firmware to ESP32 (Direct USB)

1. Open [**`esp32_firmware.ino`**](file:///c:/Users/UTKARSH%20BHANDARI/OneDrive/Desktop/sih/esp32_firmware.ino) in **Arduino IDE**.
2. **Select your mode** (line 20):
   * `#define USE_PHYSICAL_SENSORS false` : **(Recommended to test first)** The ESP32 computes realistic flight math onboard and streams it over USB Serial. No wiring required!
   * `#define USE_PHYSICAL_SENSORS true` : Reads actual physical sensors wired to the ESP32 pins.
3. Plug your ESP32 into your computer via **USB cable**.
4. In Arduino IDE:
   * **Tools > Board > ESP32 Dev Module**
   * **Tools > Port > Select your ESP32 COM port** (e.g. `COM3`, `COM4`, etc.)
5. Click **Upload** (➡️).
6. Once uploaded, close the Arduino Serial Monitor so the COM port is free for Python.

---

### Hardware Pinout Table (When using physical sensors)

| Sensor Module | Sensor Pin | ESP32 GPIO Pin | Description |
| :--- | :--- | :--- | :--- |
| **MPU6050 (IMU)** | `VCC` | `3.3V` / `5V` | Power |
| | `GND` | `GND` | Ground |
| | `SDA` | `GPIO 21` | I2C Data Line |
| | `SCL` | `GPIO 22` | I2C Clock Line |
| **BMP280 (Barometer)** | `VCC` | `3.3V` | Power |
| | `GND` | `GND` | Ground |
| | `SDA` | `GPIO 21` | Shared I2C Bus |
| | `SCL` | `GPIO 22` | Shared I2C Bus |
| **NEO-6M (GPS)** | `VCC` | `3.3V` / `5V` | Power |
| | `GND` | `GND` | Ground |
| | `TX` | `GPIO 16 (RX2)` | Hardware Serial2 RX |
| | `RX` | `GPIO 17 (TX2)` | Hardware Serial2 TX |

---

## 📡 Step 3: Run the Receiver on Your Computer

In your terminal (with `.venv` active):

```bash
python reciever.py
```

### What Happens:
1. `reciever.py` **auto-scans all COM ports** and connects directly to your ESP32 over USB at **115200 baud**.
2. If the ESP32 is plugged in and transmitting:
   * Title turns green: `Live 2D Trajectory [LIVE HARDWARE: USB COMx]`.
   * Real sensor readings are cleaned of spikes and plotted in real time.
3. If the ESP32 is unplugged:
   * After 3.0 seconds, it seamlessly falls back to `[MOCK FALLBACK]` simulated data.
   * When you plug the ESP32 back in, it resumes live hardware data instantly!

---

## 📦 Telemetry Packet Format

Data is streamed as comma-separated values (CSV) over Serial at 10 Hz:

```text
timestamp,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,pressure,temperature,distance,latitude,longitude,gps_altitude
```

---

## 💾 Recorded Flight Data
All processed packets are automatically saved to [**`flight_telemetry_log.csv`**](file:///c:/Users/UTKARSH%20BHANDARI/OneDrive/Desktop/sih/flight_telemetry_log.csv) for post-flight trajectory analysis in Excel or Python.
