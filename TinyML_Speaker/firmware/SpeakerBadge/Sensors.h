#pragma once
#include <Arduino_BMI270_BMM150.h>
#include <Arduino_HS300x.h>
#include <Arduino_LPS22HB.h>
#include <Arduino_APDS9960.h>
#include <Wire.h>
#include <mbed.h>

// Combined IMU read and register setup follow Nano33SenseRev2_SerialRealtime.
class FastImu : public BoschSensorClass {
 public:
  using BoschSensorClass::BoschSensorClass;
  bool readMotion(float *values) {
    bmi2_sens_data data;
    if (!device || bmi2_get_sensor_data(&data, device) != BMI2_OK) return false;
    values[0] = -data.acc.y / 8192.0f;
    values[1] = -data.acc.x / 8192.0f;
    values[2] = data.acc.z / 8192.0f;
    values[3] = -data.gyr.y / 16.384f;
    values[4] = data.gyr.x / 16.384f;
    values[5] = data.gyr.z / 16.384f;
    return true;
  }
 protected:
  int8_t configure_sensor(bmi2_dev *value) override {
    device = value;
    int8_t result = BoschSensorClass::configure_sensor(value);
    return result != BMI2_OK ? result : bmi2_set_adv_power_save(BMI2_DISABLE, value);
  }
 private:
  bmi2_dev *device = nullptr;
};

class SensorBank {
 public:
  FastImu imu{Wire1};
  rtos::Mutex mutex;
  float auxiliary[5] = {NAN, NAN, NAN, NAN, NAN}; // magnetic, temperature, humidity, pressure, proximity
  bool begin() {
    if (!imu.begin()) return false;
    hasHS = HS300x.begin();
    hasPressure = BARO.begin();
    hasProximity = APDS.begin();
    Wire1.setClock(400000);
    if (hasPressure) writeRegister(0x5C, 0x10, 0x22);
    return true;
  }
  bool setRate(uint16_t rate) {
    mbed::ScopedLock<rtos::Mutex> lock(mutex);
    for (uint8_t reg : {0x40, 0x42}) {
      int value = readRegister(0x68, reg);
      if (value < 0 || !writeRegister(0x68, reg, (value & 0xF0) | (rate > 100 ? 0x09 : 0x08))) return false;
    }
    return true;
  }
  void poll(uint32_t now) {
    if (now - lastMag >= 20) {
      mbed::ScopedLock<rtos::Mutex> lock(mutex);
      float x, y, z;
      if (imu.magneticFieldAvailable() && imu.readMagneticField(x, y, z)) auxiliary[0] = sqrtf(x*x + y*y + z*z);
      lastMag = now;
    }
    if (hasHS && pendingHS && now - hsStarted >= 40) {
      mbed::ScopedLock<rtos::Mutex> lock(mutex);
      if (Wire1.requestFrom(static_cast<uint8_t>(0x44), static_cast<uint8_t>(4)) == 4) {
        uint16_t h = Wire1.read() << 8;
        h |= Wire1.read();
        uint16_t t = Wire1.read() << 8;
        t |= Wire1.read();
        if ((h >> 14) == 0 && (h & 0x3FFF) != 0x3FFF && (t >> 2) != 0x3FFF) {
          auxiliary[1] = (t >> 2) * .010071415f - 40;
          auxiliary[2] = (h & 0x3FFF) * .006163516f;
        }
      }
      pendingHS = false;
      nextHS = now + 500;
    } else if (hasHS && !pendingHS && static_cast<int32_t>(now - nextHS) >= 0) {
      mbed::ScopedLock<rtos::Mutex> lock(mutex);
      Wire1.beginTransmission(0x44);
      Wire1.write(static_cast<uint8_t>(0));
      pendingHS = Wire1.endTransmission(true) == 0;
      hsStarted = now;
      nextHS = now + 1000;
    }
    if (hasPressure && now - lastPressure >= 100) {
      mbed::ScopedLock<rtos::Mutex> lock(mutex);
      int a = readRegister(0x5C, 0x28), b = readRegister(0x5C, 0x29), c = readRegister(0x5C, 0x2A);
      if (a >= 0 && b >= 0 && c >= 0) auxiliary[3] = (a | (b << 8) | (c << 16)) / 40960.0f;
      lastPressure = now;
    }
    if (hasProximity && now - lastProximity >= 20) {
      mbed::ScopedLock<rtos::Mutex> lock(mutex);
      if (APDS.proximityAvailable()) auxiliary[4] = APDS.readProximity();
      lastProximity = now;
    }
  }
 private:
  bool hasHS = false, hasPressure = false, hasProximity = false, pendingHS = false;
  uint32_t lastMag = 0, lastPressure = 0, lastProximity = 0, hsStarted = 0, nextHS = 0;
  static int readRegister(uint8_t address, uint8_t reg) {
    Wire1.beginTransmission(address);
    Wire1.write(reg);
    if (Wire1.endTransmission(false) || Wire1.requestFrom(address, static_cast<uint8_t>(1)) != 1) return -1;
    return Wire1.read();
  }
  static bool writeRegister(uint8_t address, uint8_t reg, uint8_t value) {
    Wire1.beginTransmission(address);
    Wire1.write(reg);
    Wire1.write(value);
    return Wire1.endTransmission() == 0;
  }
};
