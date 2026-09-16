/*
 * =====================================================================
 * ESP32 Direct Hardware Serial (USB) Telemetry Transmitter
 * ---------------------------------------------------------------------
 * Connection: DIRECT USB CABLE to Computer (No Wi-Fi Needed!)
 * Baud Rate:  115200
 * 
 * Packet Format (CSV):
 * timestamp,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,pressure,temp,distance,lat,lon,alt
 * =====================================================================
 */

#include <Wire.h>

// =====================================================
// 1. CONFIGURATION
// =====================================================
#define SERIAL_BAUD_RATE 115200

// Set to true if physical sensors (MPU6050, BMP280, GPS) are wired to the ESP32.
// Set to false to let the ESP32 compute realistic flight telemetry math onboard.
#define USE_PHYSICAL_SENSORS false

// Telemetry streaming interval (10 Hz = 100ms)
const unsigned long SEND_INTERVAL_MS = 100;

// =====================================================
// 2. SENSOR PINS (When USE_PHYSICAL_SENSORS is true)
// =====================================================
// I2C Sensors (MPU6050 IMU & BMP280 Barometer):
//   ESP32 GPIO 21 -> SDA
//   ESP32 GPIO 22 -> SCL
//   ESP32 3.3V    -> VCC
//   ESP32 GND     -> GND
//
// GPS Module (NEO-6M / similar):
//   ESP32 GPIO 16 (RX2) -> GPS TX
//   ESP32 GPIO 17 (TX2) -> GPS RX
// =====================================================

unsigned long packet_counter = 0;
unsigned long last_send_time = 0;

// Base coordinates for GPS simulation
const float BASE_LAT = 28.613900;
const float BASE_LON = 77.209000;
const float BASE_ALT = 35.2;

void setup() {
  // Initialize USB Serial communication with PC
  Serial.begin(SERIAL_BAUD_RATE);
  delay(1000);

  Serial.println("\n==============================================");
  Serial.println("  ESP32 DIRECT HARDWARE SERIAL TELEMETRY");
  Serial.println("  Streaming over USB at 115200 baud");
  Serial.println("==============================================");

#if USE_PHYSICAL_SENSORS
  Wire.begin(21, 22);
  Serial.println("[Sensors] Physical I2C Initialized (SDA=21, SCL=22)");
  // If using physical MPU6050 / BMP280 libraries, initialize them here
#else
  Serial.println("[Mode] Running onboard realistic flight simulation.");
#endif
}

void loop() {
  unsigned long current_time = millis();

  // Send packet every 100ms (10 Hz rate)
  if (current_time - last_send_time >= SEND_INTERVAL_MS) {
    last_send_time = current_time;

    float accel_x, accel_y, accel_z;
    float gyro_x, gyro_y, gyro_z;
    float pressure, temperature;
    float distance;
    float latitude, longitude, gps_altitude;

#if USE_PHYSICAL_SENSORS
    // --- READ PHYSICAL SENSORS ---
    // (Replace with your actual sensor library function calls)
    accel_x = 0.08; 
    accel_y = -0.01; 
    accel_z = 9.81;
    gyro_x = 0.01; 
    gyro_y = 0.02; 
    gyro_z = -0.01;
    pressure = 1013.25;
    temperature = 25.4;
    distance = 38.5;
    latitude = BASE_LAT;
    longitude = BASE_LON;
    gps_altitude = BASE_ALT;
#else
    // --- REALISTIC ONBOARD TRAJECTORY MATHEMATICS ---
    float t = (float)packet_counter / 10.0;
    float horizontal_m = t * 1.2;
    float height_m = 3.5 * sin(t * 0.4) + 0.6 * t;

    accel_x = 0.12 + 0.05 * sin(t);
    accel_y = -0.03 + 0.03 * cos(t);
    accel_z = 9.81 + 0.1 * sin(2.0 * t);

    gyro_x = 0.01 + 0.005 * cos(t);
    gyro_y = 0.02 + 0.005 * sin(t);
    gyro_z = -0.01;

    pressure = 1013.25 - (height_m * 0.12);
    temperature = 25.0 - (height_m * 0.01);
    distance = max(0.0f, 100.0f - height_m);

    latitude = BASE_LAT + (height_m * 0.000009);
    longitude = BASE_LON + (horizontal_m * 0.000010);
    gps_altitude = BASE_ALT + height_m;
#endif

    // Format standard CSV packet:
    // timestamp,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,pressure,temp,distance,lat,lon,alt
    char packet[256];
    snprintf(packet, sizeof(packet),
             "%lu,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.6f,%.6f,%.2f",
             packet_counter,
             accel_x, accel_y, accel_z,
             gyro_x, gyro_y, gyro_z,
             pressure, temperature,
             distance,
             latitude, longitude, gps_altitude
    );

    // Directly print to USB Serial for the PC to read
    Serial.println(packet);

    packet_counter++;
  }
}
