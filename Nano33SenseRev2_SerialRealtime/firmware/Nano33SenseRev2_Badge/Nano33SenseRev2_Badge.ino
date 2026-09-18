/*
  Human Matrix Badge - Arduino Nano 33 BLE Sense Rev2

  Streams all available sensors over USB serial whether or not BLE is connected.
  The sample rate can be changed at runtime from the serial viewer.

  Serial commands (newline terminated):
    RATE 20       set sample rate to 20 Hz (1..25)
    STREAM ON     enable streaming
    STREAM OFF    pause streaming
    STATUS        print current status
    HELP          print command help

  Data format:
    DATA,time_ms,sound,ax,ay,az,gx,gy,gz,mx,my,mz,temp_c,humidity_pct,
         pressure_kpa,proximity,red,green,blue,ambient,gesture,gsr,rssi
*/

#include <ArduinoBLE.h>
#include <Arduino_BMI270_BMM150.h>
#include <Arduino_LPS22HB.h>
#include <Arduino_HS300x.h>
#include <Arduino_APDS9960.h>
#include <PDM.h>
#include <Wire.h>
#include <math.h>

#define NUS_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_PAYLOAD_SIZE 220

BLEService nusService(NUS_SERVICE_UUID);
BLECharacteristic txChar(NUS_TX_UUID, BLERead | BLENotify, BLE_PAYLOAD_SIZE);
BLECharacteristic rxChar(NUS_RX_UUID, BLEWriteWithoutResponse | BLEWrite, 64);

const int GSR_POWER_PIN = 7;
const int GSR_READ_PIN = A1;
const uint16_t MIN_RATE_HZ = 1;
const uint16_t MAX_RATE_HZ = 25;

short pdmBuffer[256];
volatile uint32_t soundLevel = 0;

bool hasIMU = false;
bool hasBARO = false;
bool hasHS300 = false;
bool hasAPDS = false;
bool hasPDM = false;
bool bleReady = false;
bool streaming = true;

uint16_t sampleRateHz = 10;
uint32_t sampleIntervalMs = 100;
uint32_t nextSampleMs = 0;

int lastProximity = 0;
int lastRed = 0;
int lastGreen = 0;
int lastBlue = 0;
int lastAmbient = 0;
int lastGesture = GESTURE_NONE;
float lastTemperature = NAN;
float lastHumidity = NAN;
float lastPressure = NAN;
bool hsMeasurementPending = false;
uint32_t hsRequestMs = 0;
uint32_t nextHsRequestMs = 0;
uint32_t lastPressureReadMs = 0;
uint32_t lastGesturePollMs = 0;

String serialCommand;
String bleCommand;

void onPDMdata();
void processCommand(String command, bool replyToBle = false);
void sendStatus(bool replyToBle = false);
void sendLine(const char *line);
void readCommands();
void sampleAndSend();
void updateSlowSensors();
void configurePressureContinuous();
int readI2CRegister(uint8_t address, uint8_t reg);

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(GSR_POWER_PIN, OUTPUT);
  digitalWrite(GSR_POWER_PIN, LOW);
  analogReadResolution(12);

  delay(300);
  Serial.println("INFO,Nano 33 BLE Sense Rev2 badge starting");

  hasIMU = IMU.begin();
  hasBARO = BARO.begin();
  hasHS300 = HS300x.begin();
  hasAPDS = APDS.begin();

  PDM.onReceive(onPDMdata);
  hasPDM = PDM.begin(1, 16000);

  if (hasBARO) configurePressureContinuous();

  bleReady = BLE.begin();
  if (bleReady) {
    BLE.setLocalName("HM Badge No.01");
    BLE.setDeviceName("HM Badge No.01");
    BLE.setAdvertisedService(nusService);
    nusService.addCharacteristic(txChar);
    nusService.addCharacteristic(rxChar);
    BLE.addService(nusService);
    BLE.advertise();
  }

  Serial.println("HEADER,time_ms,sound,ax,ay,az,gx,gy,gz,mx,my,mz,temp_c,humidity_pct,pressure_kpa,proximity,red,green,blue,ambient,gesture,gsr,rssi");
  sendStatus();
  Serial.println("INFO,Commands: RATE <1-25>, STREAM ON, STREAM OFF, STATUS, HELP");
  nextSampleMs = millis();
}

void loop() {
  if (bleReady) BLE.poll();
  readCommands();
  updateSlowSensors();

  const uint32_t now = millis();
  if (streaming && (int32_t)(now - nextSampleMs) >= 0) {
    sampleAndSend();
    nextSampleMs += sampleIntervalMs;
    if ((int32_t)(now - nextSampleMs) >= 0) nextSampleMs = now + sampleIntervalMs;
  }

  digitalWrite(LED_BUILTIN, bleReady && BLE.connected() ? HIGH : LOW);
}

void readCommands() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialCommand.length()) {
        processCommand(serialCommand);
        serialCommand = "";
      }
    } else if (serialCommand.length() < 63) {
      serialCommand += c;
    }
  }

  if (bleReady && rxChar.written()) {
    const int length = rxChar.valueLength();
    const uint8_t *value = rxChar.value();
    for (int i = 0; i < length; ++i) {
      char c = (char)value[i];
      if (c == '\n' || c == '\r') {
        if (bleCommand.length()) {
          processCommand(bleCommand, true);
          bleCommand = "";
        }
      } else if (bleCommand.length() < 63) {
        bleCommand += c;
      }
    }
    // BLE terminal apps often write a command without a trailing newline.
    if (bleCommand.length()) {
      processCommand(bleCommand, true);
      bleCommand = "";
    }
  }
}

void processCommand(String command, bool replyToBle) {
  command.trim();
  command.toUpperCase();

  if (command.startsWith("RATE ") || command.startsWith("RATE=")) {
    const int separator = command.indexOf(' ') >= 0 ? command.indexOf(' ') : command.indexOf('=');
    const long requested = command.substring(separator + 1).toInt();
    if (requested >= MIN_RATE_HZ && requested <= MAX_RATE_HZ) {
      sampleRateHz = (uint16_t)requested;
      sampleIntervalMs = 1000UL / sampleRateHz;
      nextSampleMs = millis() + sampleIntervalMs;
      char response[48];
      snprintf(response, sizeof(response), "OK,RATE,%u", sampleRateHz);
      Serial.println(response);
      if (replyToBle && bleReady && BLE.connected()) txChar.writeValue(response);
    } else {
      Serial.println("ERROR,RATE must be 1..25 Hz");
    }
  } else if (command == "STREAM ON") {
    streaming = true;
    nextSampleMs = millis();
    Serial.println("OK,STREAM,ON");
  } else if (command == "STREAM OFF") {
    streaming = false;
    Serial.println("OK,STREAM,OFF");
  } else if (command == "STATUS") {
    sendStatus(replyToBle);
  } else if (command == "HELP") {
    Serial.println("INFO,Commands: RATE <1-25>, STREAM ON, STREAM OFF, STATUS, HELP");
  } else if (command.length()) {
    Serial.println("ERROR,Unknown command; send HELP");
  }
}

void sendStatus(bool replyToBle) {
  char status[180];
  snprintf(status, sizeof(status),
           "STATUS,rate_hz=%u,stream=%s,imu=%d,baro=%d,hs300=%d,apds=%d,pdm=%d,ble=%d",
           sampleRateHz, streaming ? "on" : "off", hasIMU, hasBARO,
           hasHS300, hasAPDS, hasPDM, bleReady);
  Serial.println(status);
  if (replyToBle && bleReady && BLE.connected()) txChar.writeValue(status);
}

void sampleAndSend() {
  float ax = NAN, ay = NAN, az = NAN;
  float gx = NAN, gy = NAN, gz = NAN;
  float mx = NAN, my = NAN, mz = NAN;
  if (hasIMU) {
    if (IMU.accelerationAvailable()) IMU.readAcceleration(ax, ay, az);
    if (IMU.gyroscopeAvailable()) IMU.readGyroscope(gx, gy, gz);
    if (IMU.magneticFieldAvailable()) IMU.readMagneticField(mx, my, mz);
  }
  digitalWrite(GSR_POWER_PIN, HIGH);
  delayMicroseconds(5000);
  const int gsrRaw = analogRead(GSR_READ_PIN);
  digitalWrite(GSR_POWER_PIN, LOW);
  const int gsr = constrain(map(gsrRaw, 0, 4095, 0, 255), 0, 255);

  int rssi = 0;
  if (bleReady && BLE.connected()) rssi = BLE.central().rssi();

  char line[BLE_PAYLOAD_SIZE];
  snprintf(line, sizeof(line),
           "DATA,%lu,%lu,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%d,%d,%d,%d,%d,%d,%d,%d",
           millis(), (unsigned long)soundLevel,
           ax, ay, az, gx, gy, gz, mx, my, mz,
           lastTemperature, lastHumidity, lastPressure,
           lastProximity, lastRed, lastGreen, lastBlue, lastAmbient,
           lastGesture, gsr, rssi);
  lastGesture = GESTURE_NONE;
  sendLine(line);
}

void sendLine(const char *line) {
  Serial.println(line);
  if (bleReady && BLE.connected()) {
    txChar.writeValue((const uint8_t *)line, strlen(line));
  }
}

// Environmental sensors are updated without blocking the fast sample loop.
// HS3003 conversions are started and collected on separate passes. LPS22HB is
// placed in continuous mode so pressure reads never wait for a one-shot sample.
void updateSlowSensors() {
  const uint32_t now = millis();

  if (hasHS300) {
    if (hsMeasurementPending && now - hsRequestMs >= 40) {
      if (Wire1.requestFrom((uint8_t)0x44, (uint8_t)4) == 4) {
        const uint16_t rawHumidityWithStatus = ((uint16_t)Wire1.read() << 8) | Wire1.read();
        const uint16_t rawTemperatureWithStatus = ((uint16_t)Wire1.read() << 8) | Wire1.read();
        const uint8_t status = rawHumidityWithStatus >> 14;
        const uint16_t rawHumidity = rawHumidityWithStatus & 0x3FFF;
        const uint16_t rawTemperature = rawTemperatureWithStatus >> 2;
        if (status == 0 && rawHumidity != 0x3FFF && rawTemperature != 0x3FFF) {
          lastHumidity = rawHumidity * 0.006163516f;
          lastTemperature = rawTemperature * 0.010071415f - 40.0f;
        }
      }
      hsMeasurementPending = false;
      nextHsRequestMs = now + 500;
    } else if (!hsMeasurementPending && (int32_t)(now - nextHsRequestMs) >= 0) {
      Wire1.beginTransmission(0x44);
      Wire1.write((uint8_t)0);
      if (Wire1.endTransmission(true) == 0) {
        hsMeasurementPending = true;
        hsRequestMs = now;
      } else {
        nextHsRequestMs = now + 1000;
      }
    }
  }

  if (hasBARO && now - lastPressureReadMs >= 100) {
    const int xl = readI2CRegister(0x5C, 0x28);
    const int low = readI2CRegister(0x5C, 0x29);
    const int high = readI2CRegister(0x5C, 0x2A);
    if (xl >= 0 && low >= 0 && high >= 0) {
      const uint32_t raw = (uint32_t)xl | ((uint32_t)low << 8) | ((uint32_t)high << 16);
      lastPressure = raw / 40960.0f;
    }
    lastPressureReadMs = now;
  }

  if (hasAPDS) {
    if (now - lastGesturePollMs >= 250) {
      if (APDS.gestureAvailable()) lastGesture = APDS.readGesture();
      lastGesturePollMs = now;
    }
    if (APDS.proximityAvailable()) lastProximity = APDS.readProximity();
    if (APDS.colorAvailable()) APDS.readColor(lastRed, lastGreen, lastBlue, lastAmbient);
  }
}

void configurePressureContinuous() {
  Wire1.beginTransmission(0x5C);
  Wire1.write((uint8_t)0x10);  // CTRL_REG1
  Wire1.write((uint8_t)0x22);  // 10 Hz output data rate + block data update
  Wire1.endTransmission();
}

int readI2CRegister(uint8_t address, uint8_t reg) {
  Wire1.beginTransmission(address);
  Wire1.write(reg);
  if (Wire1.endTransmission(false) != 0) return -1;
  if (Wire1.requestFrom(address, (uint8_t)1) != 1) return -1;
  return Wire1.read();
}

void onPDMdata() {
  const int bytesAvailable = min(PDM.available(), (int)sizeof(pdmBuffer));
  if (bytesAvailable <= 0) return;
  PDM.read(pdmBuffer, bytesAvailable);
  const int count = bytesAvailable / (int)sizeof(short);
  uint64_t sumSquares = 0;
  for (int i = 0; i < count; ++i) {
    const int32_t sample = pdmBuffer[i];
    sumSquares += (uint64_t)(sample * sample);
  }
  soundLevel = count ? (uint32_t)sqrt((double)sumSquares / count) : 0;
}
