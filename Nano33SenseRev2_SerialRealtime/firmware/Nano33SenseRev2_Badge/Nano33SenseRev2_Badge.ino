/*
  Human Matrix Badge - Arduino Nano 33 BLE Sense Rev2

  Streams all available sensors over USB serial whether or not BLE is connected.
  Sampling and sending are independent: a high-priority thread, woken by a
  microsecond ticker, samples into a 128 KB buffer, and loop() sends the buffer
  every SEND interval. The separate thread matters once BLE is running: the BLE
  stack's thread can hold the CPU for 5 ms at a time, which a loop() based
  sampler cannot preempt.

  Serial commands (newline terminated):
    RATE 100      set sample rate to 100 Hz (1..200)
    SEND 30s      send buffered samples every 30 seconds. Accepts ms (default),
                  s, or min, e.g. SEND 250, SEND 15s, SEND 1min. SEND 0 sends
                  samples as soon as possible. Max 10 min.
    STREAM ON     enable streaming
    STREAM OFF    pause streaming
    STATUS        print current status
    HELP          print command help

  The buffer holds about 60 s at 100 Hz, 30 s at 200 Hz, and longer at lower
  rates (STATUS reports capacity_s). If the SEND interval is longer, samples
  are sent when the buffer is nearly full.

  Data format:
    DATA,time_ms,sound,ax,ay,az,gx,gy,gz,mx,my,mz,temp_c,humidity_pct,
         pressure_kpa,proximity,red,green,blue,ambient,gesture,gsr,rssi,seq

  seq increments once per scheduled sample, so a gap means samples were
  dropped because the output could not keep up with the sample rate.

  Samples are buffered as binary packets, which are sent as-is over BLE and
  expanded into DATA rows for USB. Text replies (OK, STATUS) are
  newline-terminated text. A packet starts with 0x02 and is little-endian:

    header (36 bytes)
      u8  type = 0x02        u8  count
      u32 seq of sample 0    u32 time_ms of sample 0
      i16 mx, my, mz (uT x10)
      i16 temp_c (x100)      u16 humidity_pct (x100)   u32 pressure (Pa)
      u8  proximity          u16 red, green, blue, ambient
      i8  gesture            u8  gsr                   i8  rssi
    count samples (16 bytes each), with consecutive seq values
      u16 time_ms - header time_ms    u16 sound
      i16 ax, ay, az (g x1000)        i16 gx, gy, gz (dps x16)

  A packet spans at most 100 ms. Slow fields are read when it starts; gesture
  is the first gesture seen during it. Missing values are 0x8000 for signed
  fields and all ones for unsigned fields.
*/

#include <ArduinoBLE.h>
#include <Arduino_BMI270_BMM150.h>
#include <Arduino_LPS22HB.h>
#include <Arduino_HS300x.h>
#include <Arduino_APDS9960.h>
#include <PDM.h>
#include <Wire.h>
#include <math.h>
#include <atomic>
#include <mbed.h>

#define NUS_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
// Fits a 247-byte ATT MTU, which Windows, macOS, and Android negotiate.
#define BLE_PAYLOAD_SIZE 244

BLEService nusService(NUS_SERVICE_UUID);
BLECharacteristic txChar(NUS_TX_UUID, BLERead | BLENotify, BLE_PAYLOAD_SIZE);
BLECharacteristic rxChar(NUS_RX_UUID, BLEWriteWithoutResponse | BLEWrite, 64);

// Reads acceleration and rotation with one register read, where the library
// reads both twice. Advanced power save is turned off because it makes the
// Bosch driver wait 450 us around every register access.
class BadgeImu : public BoschSensorClass {
 public:
  using BoschSensorClass::BoschSensorClass;

  bool readMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    struct bmi2_sens_data data;
    if (!motionDevice || bmi2_get_sensor_data(&data, motionDevice) != BMI2_OK) return false;
    // Same scaling (+-4 g, +-2000 dps) and board axis mapping as the library.
    ax = -data.acc.y / 8192.0f;
    ay = -data.acc.x / 8192.0f;
    az = data.acc.z / 8192.0f;
    gx = -data.gyr.y / 16.384f;
    gy = -data.gyr.x / 16.384f;
    gz = data.gyr.z / 16.384f;
    return true;
  }

 protected:
  int8_t configure_sensor(struct bmi2_dev *dev) override {
    motionDevice = dev;
    const int8_t result = BoschSensorClass::configure_sensor(dev);
    return result != BMI2_OK ? result : bmi2_set_adv_power_save(BMI2_DISABLE, dev);
  }

 private:
  struct bmi2_dev *motionDevice = nullptr;
};

BadgeImu imu(Wire1);

const int GSR_POWER_PIN = 7;
const int GSR_READ_PIN = A1;
const uint16_t MIN_RATE_HZ = 1;
const uint16_t MAX_RATE_HZ = 200;
const uint32_t MAX_SEND_INTERVAL_MS = 600000;
const uint32_t I2C_CLOCK_HZ = 400000;
const uint32_t GSR_PERIOD_MS = 40;
const uint32_t GSR_SETTLE_US = 5000;

const uint8_t PACKET_TYPE = 0x02;
const size_t PACKET_HEADER_SIZE = 36;
const size_t PACKET_SAMPLE_SIZE = 16;
const size_t PACKET_MAX_SIZE = BLE_PAYLOAD_SIZE;
const uint8_t PACKET_MAX_SAMPLES = (PACKET_MAX_SIZE - PACKET_HEADER_SIZE) / PACKET_SAMPLE_SIZE;
const size_t PACKET_GESTURE_OFFSET = PACKET_HEADER_SIZE - 3;
// Bounds how stale a packet's slow-sensor snapshot gets, and how long SEND 0
// waits before sending.
const uint32_t PACKET_MAX_SPAN_MS = 100;
// A power of two, so ring positions stay consistent when they wrap at 2^32.
const uint32_t RING_SIZE = 131072;
// Buffered data is sent early once free space drops below this.
const uint32_t SEND_EARLY_FREE_BYTES = 6144;
// Sending is spread over loop passes so a long burst does not stall the slow
// sensors or command handling.
const uint8_t PACKETS_PER_LOOP = 4;

short pdmBuffer[256];
volatile uint32_t soundLevel = 0;

bool hasIMU = false;
bool hasBARO = false;
bool hasHS300 = false;
bool hasAPDS = false;
bool hasPDM = false;
bool bleReady = false;
volatile bool streaming = true;

uint16_t sampleRateHz = 10;
uint32_t sendIntervalMs = 0;
uint32_t nextSendMs = 0;

// The sampler thread fills packets in the ring and publishes each closed one
// by advancing ringWrite. loop() sends closed packets and advances ringRead.
// Wire1 is shared, so every I2C access holds i2cMutex.
rtos::Thread samplerThread(osPriorityHigh, 4096);
rtos::EventFlags samplerFlags;
rtos::Mutex i2cMutex;
mbed::Ticker sampleTicker;
std::atomic<uint32_t> pendingTicks(0);

uint8_t ring[RING_SIZE];
std::atomic<uint32_t> ringWrite(0);  // end of the last closed packet
std::atomic<uint32_t> ringRead(0);   // start of the next unsent packet
uint32_t sendTarget = 0;             // loop() sends until ringRead reaches this
uint32_t openPos = 0;                // packet being filled by the sampler
uint8_t openCount = 0;
uint32_t openTimeMs = 0;
uint32_t sampleSeq = 0;
volatile uint32_t droppedSamples = 0;

float lastAx = NAN, lastAy = NAN, lastAz = NAN;
float lastGx = NAN, lastGy = NAN, lastGz = NAN;
float lastMx = NAN, lastMy = NAN, lastMz = NAN;
int lastGsr = 0;
int lastRssi = 0;
int lastProximity = 0;
int lastRed = 0;
int lastGreen = 0;
int lastBlue = 0;
int lastAmbient = 0;
std::atomic<int> lastGesture(GESTURE_NONE);
float lastTemperature = NAN;
float lastHumidity = NAN;
float lastPressure = NAN;
bool hsMeasurementPending = false;
uint32_t hsRequestMs = 0;
uint32_t nextHsRequestMs = 0;
uint32_t lastPressureReadMs = 0;
uint32_t lastGesturePollMs = 0;
uint32_t lastApdsPollMs = 0;
uint32_t lastMagPollMs = 0;
uint32_t lastRssiPollMs = 0;
bool gsrPowered = false;
uint32_t gsrPowerOnUs = 0;
uint32_t lastGsrReadMs = 0;

String serialCommand;
String bleCommand;

void onPDMdata();
void processCommand(String command, bool replyToBle = false);
void sendStatus(bool replyToBle = false);
long parseDurationMs(String value);
void warnIfSendExceedsCapacity(bool replyToBle);
void readCommands();
void scheduleSend();
uint32_t capacitySeconds();
void onSampleTick();
void samplerLoop();
bool openPacket(uint32_t timeMs, uint32_t seq);
void closePacket();
void takeSample();
void drainOutput();
void printPacketRows(const uint8_t *packet);
void bleReply(const char *text);
void setSampleRate(uint16_t rateHz);
void configureImuDataRate();
void updateSlowSensors();
void configurePressureContinuous();
int readI2CRegister(uint8_t address, uint8_t reg);
bool writeI2CRegister(uint8_t address, uint8_t reg, uint8_t value);

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(GSR_POWER_PIN, OUTPUT);
  digitalWrite(GSR_POWER_PIN, LOW);
  analogReadResolution(12);

  delay(300);
  Serial.println("INFO,Nano 33 BLE Sense Rev2 badge starting");

  hasIMU = imu.begin();
  hasBARO = BARO.begin();
  hasHS300 = HS300x.begin();
  hasAPDS = APDS.begin();

  PDM.onReceive(onPDMdata);
  hasPDM = PDM.begin(1, 16000);

  if (hasBARO) configurePressureContinuous();
  // Every sensor library calls Wire1.begin(), which resets the bus clock, so
  // fast mode must be selected after all of them have started.
  Wire1.setClock(I2C_CLOCK_HZ);
  setSampleRate(sampleRateHz);

  bleReady = BLE.begin();
  if (bleReady) {
    BLE.setLocalName("HM Badge No.01");
    BLE.setDeviceName("HM Badge No.01");
    // Ask the central for a 7.5-15 ms connection interval so each connection
    // event carries fewer packets. Windows otherwise defaults to 30 ms or more.
    BLE.setConnectionInterval(6, 12);
    BLE.setAdvertisedService(nusService);
    nusService.addCharacteristic(txChar);
    nusService.addCharacteristic(rxChar);
    BLE.addService(nusService);
    BLE.advertise();
  }

  Serial.println("HEADER,time_ms,sound,ax,ay,az,gx,gy,gz,mx,my,mz,temp_c,humidity_pct,pressure_kpa,proximity,red,green,blue,ambient,gesture,gsr,rssi,seq");
  sendStatus();
  Serial.println("INFO,Commands: RATE <1-200>, SEND <0-10min> (e.g. 250, 15s, 1min), STREAM ON, STREAM OFF, STATUS, HELP");
  nextSendMs = millis();
  samplerThread.start(samplerLoop);
}

void loop() {
  if (bleReady) BLE.poll();
  readCommands();
  updateSlowSensors();
  scheduleSend();
  drainOutput();

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
      setSampleRate((uint16_t)requested);
      char response[48];
      snprintf(response, sizeof(response), "OK,RATE,%u", sampleRateHz);
      Serial.println(response);
      if (replyToBle) bleReply(response);
      warnIfSendExceedsCapacity(replyToBle);
    } else {
      Serial.println("ERROR,RATE must be 1..200 Hz");
    }
  } else if (command.startsWith("SEND ") || command.startsWith("SEND=")) {
    const int separator = command.indexOf(' ') >= 0 ? command.indexOf(' ') : command.indexOf('=');
    const long requested = parseDurationMs(command.substring(separator + 1));
    if (requested >= 0 && requested <= (long)MAX_SEND_INTERVAL_MS) {
      sendIntervalMs = (uint32_t)requested;
      nextSendMs = millis() + sendIntervalMs;
      char response[48];
      snprintf(response, sizeof(response), "OK,SEND,%lu", (unsigned long)sendIntervalMs);
      Serial.println(response);
      if (replyToBle) bleReply(response);
      warnIfSendExceedsCapacity(replyToBle);
    } else {
      Serial.println("ERROR,SEND must be 0..10min, e.g. SEND 250, SEND 15s, SEND 1min");
    }
  } else if (command == "STREAM ON") {
    pendingTicks = 0;
    streaming = true;
    nextSendMs = millis() + sendIntervalMs;
    Serial.println("OK,STREAM,ON");
  } else if (command == "STREAM OFF") {
    streaming = false;
    Serial.println("OK,STREAM,OFF");
  } else if (command == "STATUS") {
    sendStatus(replyToBle);
  } else if (command == "HELP") {
    Serial.println("INFO,Commands: RATE <1-200>, SEND <0-10min> (e.g. 250, 15s, 1min), STREAM ON, STREAM OFF, STATUS, HELP");
  } else if (command.length()) {
    Serial.println("ERROR,Unknown command; send HELP");
  }
}

void sendStatus(bool replyToBle) {
  char status[BLE_PAYLOAD_SIZE];
  snprintf(status, sizeof(status),
           "STATUS,rate_hz=%u,send_ms=%lu,stream=%s,buffered_bytes=%lu,capacity_s=%lu,dropped=%lu,"
           "imu=%d,baro=%d,hs300=%d,apds=%d,pdm=%d,ble=%d",
           sampleRateHz, (unsigned long)sendIntervalMs, streaming ? "on" : "off",
           (unsigned long)(ringWrite - ringRead), (unsigned long)capacitySeconds(), (unsigned long)droppedSamples,
           hasIMU, hasBARO, hasHS300, hasAPDS, hasPDM, bleReady);
  Serial.println(status);
  if (replyToBle) bleReply(status);
}

// Parses an upper-cased duration such as "250", "250MS", "15S", or "1MIN" into
// milliseconds. Returns -1 if it is not valid.
long parseDurationMs(String value) {
  value.trim();
  unsigned int digits = 0;
  while (digits < value.length() && isDigit(value[digits])) digits++;
  if (digits == 0 || digits > 7) return -1;
  const long number = value.substring(0, digits).toInt();
  String unit = value.substring(digits);
  unit.trim();
  if (unit == "" || unit == "MS") return number;
  if (unit == "S" || unit == "SEC") return number * 1000;
  if (unit == "M" || unit == "MIN") return number * 60000;
  return -1;
}

void warnIfSendExceedsCapacity(bool replyToBle) {
  const uint32_t capacity = capacitySeconds();
  if (sendIntervalMs <= capacity * 1000) return;
  char warning[120];
  snprintf(warning, sizeof(warning),
           "INFO,At %u Hz the buffer holds about %lu s, so data is sent whenever it fills",
           sampleRateHz, (unsigned long)capacity);
  Serial.println(warning);
  if (replyToBle) bleReply(warning);
}

void setSampleRate(uint16_t rateHz) {
  sampleRateHz = rateHz;
  configureImuDataRate();
  sampleTicker.attach(onSampleTick, std::chrono::microseconds(1000000UL / sampleRateHz));
}

// The IMU library fixes the BMI270 at 100 Hz. Raise its output data rate when
// the badge samples faster so every sample sees a fresh reading.
void configureImuDataRate() {
  if (!hasIMU) return;
  mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
  const uint8_t bmiAddress = 0x68;
  const uint8_t odrCode = sampleRateHz > 100 ? 0x09 : 0x08;  // 200 Hz : 100 Hz
  const uint8_t confRegisters[] = {0x40, 0x42};                // ACC_CONF, GYR_CONF
  for (uint8_t reg : confRegisters) {
    const int current = readI2CRegister(bmiAddress, reg);
    if (current < 0) continue;
    writeI2CRegister(bmiAddress, reg, (uint8_t)((current & 0xF0) | odrCode));
    delay(1);  // BMI270 needs >450 us between writes in low-power mode
  }
}

// Marks buffered packets as ready to send once the SEND interval elapses, or
// early if the buffer is nearly full. With SEND 0, or while paused, everything
// buffered is sent right away.
void scheduleSend() {
  const uint32_t now = millis();
  bool send = !streaming || !sendIntervalMs;
  if (sendIntervalMs && (int32_t)(now - nextSendMs) >= 0) {
    send = true;
    nextSendMs += sendIntervalMs;
    if ((int32_t)(now - nextSendMs) >= 0) nextSendMs = now + sendIntervalMs;
  }
  if (send || RING_SIZE - (ringWrite - ringRead) < SEND_EARLY_FREE_BYTES) sendTarget = ringWrite;
}

// Approximate seconds of samples the buffer holds before it sends early.
uint32_t capacitySeconds() {
  const uint32_t intervalMs = max(1000UL / sampleRateHz, 1UL);
  const uint32_t perPacket =
      constrain((PACKET_MAX_SPAN_MS + intervalMs - 1) / intervalMs, 1UL, (uint32_t)PACKET_MAX_SAMPLES);
  const uint32_t bytesPerSecond = sampleRateHz * (PACKET_HEADER_SIZE + perPacket * PACKET_SAMPLE_SIZE) / perPacket;
  return (RING_SIZE - SEND_EARLY_FREE_BYTES - PACKET_MAX_SIZE) / bytesPerSecond;
}

void onSampleTick() {
  pendingTicks++;
  samplerFlags.set(1);
}

// Runs above loop() and the BLE stack's thread, so a sample is taken as soon
// as the ticker fires. Ticks that arrive while a sample is still being taken
// are counted as dropped.
void samplerLoop() {
  while (true) {
    samplerFlags.wait_any(1);
    const uint32_t ticks = pendingTicks.exchange(0);
    if (!streaming) {
      closePacket();
      continue;
    }
    if (!ticks) continue;
    if (ticks > 1) {
      droppedSamples += ticks - 1;
      sampleSeq += ticks - 1;
      closePacket();  // samples within a packet have consecutive seq values
    }
    takeSample();
  }
}

static uint8_t *ringAt(uint32_t pos) { return &ring[pos % RING_SIZE]; }

static size_t packetSize(uint8_t count) { return PACKET_HEADER_SIZE + count * PACKET_SAMPLE_SIZE; }

// Packets never wrap around the end of the ring; one that would not fit
// starts at the beginning instead.
static uint32_t packetStart(uint32_t pos) {
  const uint32_t room = RING_SIZE - pos % RING_SIZE;
  return room < PACKET_MAX_SIZE ? pos + room : pos;
}

static uint8_t *putU8(uint8_t *p, uint8_t value) {
  *p = value;
  return p + 1;
}

static uint8_t *putU16(uint8_t *p, uint16_t value) {
  p[0] = value & 0xFF;
  p[1] = value >> 8;
  return p + 2;
}

static uint8_t *putU32(uint8_t *p, uint32_t value) { return putU16(putU16(p, value & 0xFFFF), value >> 16); }

// Scales a float to int16, using 0x8000 for missing or out-of-range values.
static uint8_t *putScaled(uint8_t *p, float value, float scale) {
  const float scaled = roundf(value * scale);
  const bool valid = isfinite(scaled) && scaled > -32768.0f && scaled <= 32767.0f;
  return putU16(p, valid ? (uint16_t)(int16_t)scaled : 0x8000);
}

// Scales a non-negative float, using `missing` for missing or out-of-range values.
static uint32_t scaleUnsigned(float value, float scale, uint32_t missing) {
  const float scaled = roundf(value * scale);
  return isfinite(scaled) && scaled >= 0.0f && scaled < (float)missing ? (uint32_t)scaled : missing;
}

static uint16_t getU16(const uint8_t *p) { return p[0] | (p[1] << 8); }

static uint32_t getU32(const uint8_t *p) { return getU16(p) | ((uint32_t)getU16(p + 2) << 16); }

static float getScaled(const uint8_t *p, float scale) {
  const int16_t raw = (int16_t)getU16(p);
  return raw == INT16_MIN ? NAN : raw / scale;
}

static float getUnsignedScaled(uint32_t raw, float scale, uint32_t missing) {
  return raw == missing ? NAN : raw / scale;
}

// Starts a packet with a snapshot of the slow sensors. Returns false if the
// buffer is full.
bool openPacket(uint32_t timeMs, uint32_t seq) {
  const uint32_t pos = packetStart(ringWrite);
  if (pos + PACKET_MAX_SIZE - ringRead > RING_SIZE) return false;
  uint8_t *p = ringAt(pos);
  p = putU8(p, PACKET_TYPE);
  p = putU8(p, 0);  // count, filled in by closePacket()
  p = putU32(p, seq);
  p = putU32(p, timeMs);
  p = putScaled(p, lastMx, 10.0f);
  p = putScaled(p, lastMy, 10.0f);
  p = putScaled(p, lastMz, 10.0f);
  p = putScaled(p, lastTemperature, 100.0f);
  p = putU16(p, (uint16_t)scaleUnsigned(lastHumidity, 100.0f, 0xFFFF));
  p = putU32(p, scaleUnsigned(lastPressure, 1000.0f, 0xFFFFFFFF));
  p = putU8(p, (uint8_t)constrain(lastProximity, 0, 255));
  p = putU16(p, (uint16_t)lastRed);
  p = putU16(p, (uint16_t)lastGreen);
  p = putU16(p, (uint16_t)lastBlue);
  p = putU16(p, (uint16_t)lastAmbient);
  p = putU8(p, (uint8_t)GESTURE_NONE);
  p = putU8(p, (uint8_t)lastGsr);
  putU8(p, (uint8_t)(int8_t)constrain(lastRssi, -128, 127));
  openPos = pos;
  openTimeMs = timeMs;
  return true;
}

void closePacket() {
  if (!openCount) return;
  ringAt(openPos)[1] = openCount;
  ringWrite = openPos + packetSize(openCount);
  openCount = 0;
}

// Reads only the fast-changing motion data; everything else uses the latest
// value collected by updateSlowSensors().
void takeSample() {
  const uint32_t timeMs = millis();
  if (hasIMU) {
    mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
    imu.readMotion(lastAx, lastAy, lastAz, lastGx, lastGy, lastGz);
  }

  const uint32_t seq = sampleSeq++;
  if (!openCount && !openPacket(timeMs, seq)) {
    droppedSamples++;
    return;
  }

  uint8_t *packet = ringAt(openPos);
  uint8_t *p = packet + packetSize(openCount);
  p = putU16(p, (uint16_t)(timeMs - openTimeMs));
  p = putU16(p, (uint16_t)min(soundLevel, (uint32_t)0xFFFF));
  p = putScaled(p, lastAx, 1000.0f);
  p = putScaled(p, lastAy, 1000.0f);
  p = putScaled(p, lastAz, 1000.0f);
  p = putScaled(p, lastGx, 16.0f);
  p = putScaled(p, lastGy, 16.0f);
  putScaled(p, lastGz, 16.0f);
  const int gesture = lastGesture.exchange(GESTURE_NONE);
  if (gesture != GESTURE_NONE && (int8_t)packet[PACKET_GESTURE_OFFSET] == GESTURE_NONE) {
    packet[PACKET_GESTURE_OFFSET] = (uint8_t)gesture;
  }
  openCount++;

  // Close the packet when it is full or the next sample would exceed its span.
  const uint32_t intervalMs = 1000UL / sampleRateHz;
  if (openCount >= PACKET_MAX_SAMPLES || timeMs - openTimeMs + intervalMs >= PACKET_MAX_SPAN_MS) closePacket();
}

void drainOutput() {
  for (uint8_t sent = 0; sent < PACKETS_PER_LOOP && ringRead != sendTarget; ++sent) {
    const uint32_t pos = packetStart(ringRead);
    const uint8_t *packet = ringAt(pos);
    const size_t size = packetSize(packet[1]);
    printPacketRows(packet);
    if (bleReady && BLE.connected()) txChar.writeValue(packet, size);
    ringRead = pos + size;
  }
}

// Expands a packet into USB DATA rows.
void printPacketRows(const uint8_t *packet) {
  const uint8_t count = packet[1];
  const uint32_t seq = getU32(packet + 2);
  const uint32_t timeMs = getU32(packet + 6);
  const float mx = getScaled(packet + 10, 10.0f);
  const float my = getScaled(packet + 12, 10.0f);
  const float mz = getScaled(packet + 14, 10.0f);
  const float temperature = getScaled(packet + 16, 100.0f);
  const float humidity = getUnsignedScaled(getU16(packet + 18), 100.0f, 0xFFFF);
  const float pressure = getUnsignedScaled(getU32(packet + 20), 1000.0f, 0xFFFFFFFF);
  const uint8_t proximity = packet[24];
  const uint16_t red = getU16(packet + 25);
  const uint16_t green = getU16(packet + 27);
  const uint16_t blue = getU16(packet + 29);
  const uint16_t ambient = getU16(packet + 31);
  const int8_t gesture = (int8_t)packet[33];
  const uint8_t gsr = packet[34];
  const int8_t rssi = (int8_t)packet[35];

  char line[160];
  for (uint8_t i = 0; i < count; ++i) {
    const uint8_t *s = packet + packetSize(i);
    // A gesture is an event, so only the first row of a packet carries it.
    snprintf(line, sizeof(line),
             "DATA,%lu,%u,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.1f,%.1f,%.1f,%.2f,%.2f,%.3f,%u,%u,%u,%u,%u,%d,%u,%d,%lu",
             (unsigned long)(timeMs + getU16(s)), getU16(s + 2),
             getScaled(s + 4, 1000.0f), getScaled(s + 6, 1000.0f), getScaled(s + 8, 1000.0f),
             getScaled(s + 10, 16.0f), getScaled(s + 12, 16.0f), getScaled(s + 14, 16.0f),
             mx, my, mz, temperature, humidity, pressure,
             proximity, red, green, blue, ambient, i == 0 ? gesture : GESTURE_NONE, gsr, rssi,
             (unsigned long)(seq + i));
    Serial.println(line);
  }
}

// Text replies end in a newline so the viewer can tell them apart.
void bleReply(const char *text) {
  if (!bleReady || !BLE.connected()) return;
  char reply[BLE_PAYLOAD_SIZE];
  const int length = snprintf(reply, sizeof(reply), "%s\n", text);
  txChar.writeValue((const uint8_t *)reply, min(length, (int)sizeof(reply) - 1));
}

// Slow sensors are updated without blocking the sampler; each sample carries
// their latest value. HS3003 conversions are started and collected on
// separate passes. LPS22HB is placed in continuous mode so pressure reads
// never wait for a one-shot sample.
void updateSlowSensors() {
  const uint32_t now = millis();

  // GSR is powered only while it is read. The settle time is waited out across
  // loop passes instead of blocking the sampler.
  if (!gsrPowered && now - lastGsrReadMs >= GSR_PERIOD_MS) {
    digitalWrite(GSR_POWER_PIN, HIGH);
    gsrPowerOnUs = micros();
    gsrPowered = true;
  } else if (gsrPowered && micros() - gsrPowerOnUs >= GSR_SETTLE_US) {
    const int gsrRaw = analogRead(GSR_READ_PIN);
    digitalWrite(GSR_POWER_PIN, LOW);
    gsrPowered = false;
    lastGsr = constrain(map(gsrRaw, 0, 4095, 0, 255), 0, 255);
    lastGsrReadMs = now;
  }

  if (now - lastRssiPollMs >= 250) {
    lastRssi = (bleReady && BLE.connected()) ? BLE.central().rssi() : 0;
    lastRssiPollMs = now;
  }

  // The remaining sensors share the I2C bus with the sampler thread. Each
  // holds the bus only for its own reads so the sampler is never kept waiting
  // for long.

  // The BMM150 magnetometer only updates at 10 Hz.
  if (hasIMU && now - lastMagPollMs >= 20) {
    mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
    if (imu.magneticFieldAvailable()) imu.readMagneticField(lastMx, lastMy, lastMz);
    lastMagPollMs = now;
  }

  if (hasHS300) {
    if (hsMeasurementPending && now - hsRequestMs >= 40) {
      mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
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
      mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
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
    mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
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
      mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
      if (APDS.gestureAvailable()) lastGesture = APDS.readGesture();
      lastGesturePollMs = now;
    }
    if (now - lastApdsPollMs >= 20) {
      mbed::ScopedLock<rtos::Mutex> lock(i2cMutex);
      if (APDS.proximityAvailable()) lastProximity = APDS.readProximity();
      if (APDS.colorAvailable()) APDS.readColor(lastRed, lastGreen, lastBlue, lastAmbient);
      lastApdsPollMs = now;
    }
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

bool writeI2CRegister(uint8_t address, uint8_t reg, uint8_t value) {
  Wire1.beginTransmission(address);
  Wire1.write(reg);
  Wire1.write(value);
  return Wire1.endTransmission() == 0;
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
