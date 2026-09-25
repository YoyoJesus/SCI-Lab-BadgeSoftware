/*
  Human Matrix Badge - Arduino Nano 33 BLE Sense Rev2

  Streams all available sensors over USB serial whether or not BLE is connected.
  Sampling and sending are independent: a high-priority thread, woken by a
  microsecond ticker, samples into a ring buffer, and loop() sends the buffer
  every SEND milliseconds. The separate thread matters once BLE is running:
  the BLE stack's thread can hold the CPU for 5 ms at a time, which a loop()
  based sampler cannot preempt.

  Serial commands (newline terminated):
    RATE 100      set sample rate to 100 Hz (1..200)
    SEND 50       send buffered samples every 50 ms (0 = send each sample
                  immediately, max 5000)
    STREAM ON     enable streaming
    STREAM OFF    pause streaming
    STATUS        print current status
    HELP          print command help

  Data format:
    DATA,time_ms,sound,ax,ay,az,gx,gy,gz,mx,my,mz,temp_c,humidity_pct,
         pressure_kpa,proximity,red,green,blue,ambient,gesture,gsr,rssi,seq

  seq increments once per scheduled sample, so a gap means samples were
  dropped because the output could not keep up with the sample rate.

  BLE sends the same samples as binary packets, since text rows are too large
  for BLE to carry 100+ Hz. Text replies (OK, STATUS) stay newline-terminated
  text. A binary packet starts with 0x01 and is little-endian:

    header (36 bytes)
      u8  type = 0x01        u8  count
      u32 seq of sample 0    u32 time_ms of sample 0
      i16 mx, my, mz (uT x10)
      i16 temp_c (x100)      u16 humidity_pct (x100)   u32 pressure (Pa)
      u8  proximity          u16 red, green, blue, ambient
      i8  gesture            u8  gsr                   i8  rssi
    count samples (18 bytes each)
      u16 time_ms - header time_ms    u16 seq - header seq
      u16 sound
      i16 ax, ay, az (g x1000)        i16 gx, gy, gz (dps x16)

  Slow fields are taken from the first sample in the packet; gesture is the
  first gesture seen in the packet. Missing values are 0x8000 for signed
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
const uint32_t MAX_SEND_INTERVAL_MS = 5000;
const uint32_t I2C_CLOCK_HZ = 400000;
const uint32_t GSR_PERIOD_MS = 40;
const uint32_t GSR_SETTLE_US = 5000;
const uint16_t SAMPLE_BUFFER_SIZE = 512;
// Buffered samples are sent early at this fill level, before the buffer is
// full and the sampler has to drop samples.
const uint16_t SEND_EARLY_SAMPLES = SAMPLE_BUFFER_SIZE * 3 / 4;

struct Sample {
  uint32_t timeMs;
  uint32_t seq;
  uint32_t sound;
  float ax, ay, az, gx, gy, gz, mx, my, mz;
  float temperature, humidity, pressure;
  int16_t proximity, red, green, blue, ambient;
  int16_t rssi;
  int8_t gesture;
  uint8_t gsr;
};

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

// The sampler thread writes samples and producedCount; loop() reads them and
// owns sentCount and sendTarget. Wire1 is shared, so every I2C access holds
// i2cMutex.
rtos::Thread samplerThread(osPriorityHigh, 4096);
rtos::EventFlags samplerFlags;
rtos::Mutex i2cMutex;
mbed::Ticker sampleTicker;
std::atomic<uint32_t> pendingTicks(0);

Sample sampleBuffer[SAMPLE_BUFFER_SIZE];
std::atomic<uint32_t> producedCount(0);  // samples written to the buffer
std::atomic<uint32_t> sentCount(0);      // samples sent from the buffer
uint32_t sendTarget = 0;                 // send samples until sentCount reaches this
uint32_t sampleSeq = 0;
volatile uint32_t droppedSamples = 0;
const uint8_t BLE_PACKET_TYPE = 0x01;
const size_t BLE_HEADER_SIZE = 36;
const size_t BLE_SAMPLE_SIZE = 18;
const uint8_t BLE_SAMPLES_PER_PACKET = (BLE_PAYLOAD_SIZE - BLE_HEADER_SIZE) / BLE_SAMPLE_SIZE;
// A partly filled packet is held this long so each notification carries
// several samples instead of one notification per sample.
const uint32_t BLE_FLUSH_MS = 40;
uint8_t blePacket[BLE_PAYLOAD_SIZE];
uint8_t blePacketCount = 0;
size_t blePacketLength = 0;
uint32_t blePacketOpenedMs = 0;
uint32_t blePacketTimeMs = 0;
uint32_t blePacketSeq = 0;

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
void readCommands();
void scheduleSend();
void onSampleTick();
void samplerLoop();
void takeSample();
void drainOutput();
void sendSample(const Sample &sample);
void addBleSample(const Sample &sample);
void flushBlePacket();
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
  Serial.println("INFO,Commands: RATE <1-200>, SEND <0-5000 ms>, STREAM ON, STREAM OFF, STATUS, HELP");
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
    } else {
      Serial.println("ERROR,RATE must be 1..200 Hz");
    }
  } else if (command.startsWith("SEND ") || command.startsWith("SEND=")) {
    const int separator = command.indexOf(' ') >= 0 ? command.indexOf(' ') : command.indexOf('=');
    String value = command.substring(separator + 1);
    value.trim();
    const long requested = value.toInt();
    if ((requested > 0 || value == "0") && requested <= (long)MAX_SEND_INTERVAL_MS) {
      sendIntervalMs = (uint32_t)requested;
      nextSendMs = millis() + sendIntervalMs;
      char response[48];
      snprintf(response, sizeof(response), "OK,SEND,%lu", (unsigned long)sendIntervalMs);
      Serial.println(response);
      if (replyToBle) bleReply(response);
    } else {
      Serial.println("ERROR,SEND must be 0..5000 ms");
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
    Serial.println("INFO,Commands: RATE <1-200>, SEND <0-5000 ms>, STREAM ON, STREAM OFF, STATUS, HELP");
  } else if (command.length()) {
    Serial.println("ERROR,Unknown command; send HELP");
  }
}

void sendStatus(bool replyToBle) {
  char status[BLE_PAYLOAD_SIZE];
  snprintf(status, sizeof(status),
           "STATUS,rate_hz=%u,send_ms=%lu,stream=%s,buffered=%lu,dropped=%lu,"
           "imu=%d,baro=%d,hs300=%d,apds=%d,pdm=%d,ble=%d",
           sampleRateHz, (unsigned long)sendIntervalMs, streaming ? "on" : "off",
           (unsigned long)(producedCount - sentCount), (unsigned long)droppedSamples,
           hasIMU, hasBARO, hasHS300, hasAPDS, hasPDM, bleReady);
  Serial.println(status);
  if (replyToBle) bleReply(status);
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

// Marks buffered samples as ready to send once the SEND interval elapses.
// With SEND 0, or while paused, everything buffered is sent right away.
void scheduleSend() {
  const uint32_t now = millis();
  const bool nearlyFull = producedCount - sentCount >= SEND_EARLY_SAMPLES;
  if (streaming && sendIntervalMs && !nearlyFull && (int32_t)(now - nextSendMs) < 0) return;
  sendTarget = producedCount;
  if (sendIntervalMs) {
    nextSendMs += sendIntervalMs;
    if ((int32_t)(now - nextSendMs) >= 0) nextSendMs = now + sendIntervalMs;
  }
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
    if (!ticks || !streaming) continue;
    if (ticks > 1) {
      droppedSamples += ticks - 1;
      sampleSeq += ticks - 1;
    }
    takeSample();
  }
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
  if (producedCount - sentCount >= SAMPLE_BUFFER_SIZE) {
    droppedSamples++;
    return;
  }

  Sample &sample = sampleBuffer[producedCount % SAMPLE_BUFFER_SIZE];
  sample.timeMs = timeMs;
  sample.seq = seq;
  sample.sound = soundLevel;
  sample.ax = lastAx; sample.ay = lastAy; sample.az = lastAz;
  sample.gx = lastGx; sample.gy = lastGy; sample.gz = lastGz;
  sample.mx = lastMx; sample.my = lastMy; sample.mz = lastMz;
  sample.temperature = lastTemperature;
  sample.humidity = lastHumidity;
  sample.pressure = lastPressure;
  sample.proximity = lastProximity;
  sample.red = lastRed;
  sample.green = lastGreen;
  sample.blue = lastBlue;
  sample.ambient = lastAmbient;
  sample.gesture = lastGesture.exchange(GESTURE_NONE);
  sample.gsr = lastGsr;
  sample.rssi = lastRssi;
  producedCount++;
}

void drainOutput() {
  while ((int32_t)(sendTarget - sentCount) > 0) {
    sendSample(sampleBuffer[sentCount % SAMPLE_BUFFER_SIZE]);
    sentCount++;
  }
  if (blePacketCount && millis() - blePacketOpenedMs >= BLE_FLUSH_MS) flushBlePacket();
}

void sendSample(const Sample &sample) {
  char line[160];
  snprintf(line, sizeof(line),
           "DATA,%lu,%lu,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%d,%d,%d,%d,%d,%d,%d,%d,%lu",
           (unsigned long)sample.timeMs, (unsigned long)sample.sound,
           sample.ax, sample.ay, sample.az, sample.gx, sample.gy, sample.gz,
           sample.mx, sample.my, sample.mz,
           sample.temperature, sample.humidity, sample.pressure,
           sample.proximity, sample.red, sample.green, sample.blue, sample.ambient,
           sample.gesture, sample.gsr, sample.rssi, (unsigned long)sample.seq);
  Serial.println(line);
  if (bleReady && BLE.connected()) addBleSample(sample);
}

static void putU8(uint8_t value) { blePacket[blePacketLength++] = value; }

static void putU16(uint16_t value) {
  blePacket[blePacketLength++] = value & 0xFF;
  blePacket[blePacketLength++] = value >> 8;
}

static void putU32(uint32_t value) {
  putU16(value & 0xFFFF);
  putU16(value >> 16);
}

// Scales a float to int16, using 0x8000 for missing or out-of-range values.
static void putScaled(float value, float scale) {
  const float scaled = roundf(value * scale);
  const bool valid = isfinite(scaled) && scaled > -32768.0f && scaled <= 32767.0f;
  putU16(valid ? (uint16_t)(int16_t)scaled : 0x8000);
}

// Scales a non-negative float, using `missing` for missing or out-of-range values.
static uint32_t scaleUnsigned(float value, float scale, uint32_t missing) {
  const float scaled = roundf(value * scale);
  return isfinite(scaled) && scaled >= 0.0f && scaled < (float)missing ? (uint32_t)scaled : missing;
}

void addBleSample(const Sample &sample) {
  if (blePacketCount == 0) {
    blePacketLength = 0;
    blePacketOpenedMs = millis();
    blePacketTimeMs = sample.timeMs;
    blePacketSeq = sample.seq;
    putU8(BLE_PACKET_TYPE);
    putU8(0);  // count, filled in on flush
    putU32(sample.seq);
    putU32(sample.timeMs);
    putScaled(sample.mx, 10.0f);
    putScaled(sample.my, 10.0f);
    putScaled(sample.mz, 10.0f);
    putScaled(sample.temperature, 100.0f);
    putU16((uint16_t)scaleUnsigned(sample.humidity, 100.0f, 0xFFFF));
    putU32(scaleUnsigned(sample.pressure, 1000.0f, 0xFFFFFFFF));
    putU8((uint8_t)constrain(sample.proximity, 0, 255));
    putU16((uint16_t)sample.red);
    putU16((uint16_t)sample.green);
    putU16((uint16_t)sample.blue);
    putU16((uint16_t)sample.ambient);
    putU8((uint8_t)sample.gesture);
    putU8(sample.gsr);
    putU8((uint8_t)(int8_t)constrain(sample.rssi, -128, 127));
  } else if (sample.gesture != GESTURE_NONE && (int8_t)blePacket[BLE_HEADER_SIZE - 3] == GESTURE_NONE) {
    blePacket[BLE_HEADER_SIZE - 3] = (uint8_t)sample.gesture;
  }

  putU16((uint16_t)(sample.timeMs - blePacketTimeMs));
  putU16((uint16_t)(sample.seq - blePacketSeq));
  putU16((uint16_t)min(sample.sound, (uint32_t)0xFFFF));
  putScaled(sample.ax, 1000.0f);
  putScaled(sample.ay, 1000.0f);
  putScaled(sample.az, 1000.0f);
  putScaled(sample.gx, 16.0f);
  putScaled(sample.gy, 16.0f);
  putScaled(sample.gz, 16.0f);
  blePacketCount++;

  // Keep the per-packet time and seq offsets within 16 bits.
  const bool offsetsNearLimit = sample.timeMs - blePacketTimeMs > 60000 || sample.seq - blePacketSeq > 60000;
  if (blePacketCount >= BLE_SAMPLES_PER_PACKET || offsetsNearLimit) flushBlePacket();
}

void flushBlePacket() {
  if (!blePacketCount) return;
  blePacket[1] = blePacketCount;
  if (bleReady && BLE.connected()) {
    txChar.writeValue(blePacket, blePacketLength);
  }
  blePacketCount = 0;
  blePacketLength = 0;
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
