// Acquisition and bulk-output structure follows Nano33SenseRev2_SerialRealtime.
#include <ArduinoBLE.h>
#include <PDM.h>
#include <atomic>
#include "Sensors.h"
#include "SpscRing.h"
#include "Detector.h"
#if __has_include("model.h")
#include "model.h"
#define HAS_MODEL 1
#else
#define HAS_MODEL 0
#define SPEAKER_MODEL_ID "paper-rule"
#endif

BLEService service("e8310001-65d2-4b11-91e0-87f64f931c82");
BLECharacteristic readings("e8310002-65d2-4b11-91e0-87f64f931c82", BLERead | BLENotify, 244);
BLECharacteristic control("e8310003-65d2-4b11-91e0-87f64f931c82", BLEWrite, 64);
SensorBank sensors;
PaperDetector detector;

struct RawSample {
  uint32_t seq, time, dropped;
  float sound, motion[6], auxiliary[5];
};
struct Record {
  uint32_t seq, time, dropped;
  float values[13];
  uint8_t flags;
};
static_assert(sizeof(float) == 4, "Bulk protocol requires 32-bit floats");
// One slot is reserved to distinguish full from empty.
SpscRing<RawSample, 129> rawQueue;
SpscRing<Record, 1537> outputQueue;
rtos::Thread acquisitionThread(osPriorityHigh, 4096);
rtos::Thread processingThread(osPriorityAboveNormal, 4096);
rtos::EventFlags sampleFlags, processingFlags;
mbed::Ticker sampleTicker;
std::atomic<uint32_t> pendingTicks{0}, acquisitionDrops{0}, processingDrops{0};
std::atomic<bool> sampling{true}, samplerIdle{false}, processingIdle{true};
short audio[256];
volatile float soundPower = 0;
volatile uint32_t audioTime = 0;
uint32_t sampleSeq = 0, nextSend = 0, sendInterval = 5000, burstRemaining = 0;
uint16_t sampleRate = 200;
bool stopping = false;
String commandBuffer;
const uint32_t BLE_PACKET_SPACING_MS = 12;

void audioReceived() {
  int bytes = min(PDM.available(), static_cast<int>(sizeof(audio)));
  if (bytes <= 0) return;
  PDM.read(audio, bytes);
  int n = bytes / sizeof(short);
  uint64_t sum = 0;
  for (int i = 0; i < n; ++i) {
    int32_t value = audio[i];
    sum += static_cast<uint64_t>(value * value);
  }
  soundPower = n ? static_cast<float>(sum) / (2 * n) : 0;
  audioTime = millis();
}

void onSampleTick() {
  pendingTicks.fetch_add(1, std::memory_order_relaxed);
  sampleFlags.set(1);
}

void acquire() {
  while (true) {
    sampleFlags.wait_any(1);
    if (!sampling.load()) { samplerIdle.store(true); continue; }
    samplerIdle.store(false);
    uint32_t ticks = pendingTicks.exchange(0);
    if (!ticks) continue;
    if (ticks > 1) {
      acquisitionDrops.fetch_add(ticks - 1);
      sampleSeq += ticks - 1;
    }
    RawSample sample{};
    sample.seq = sampleSeq++;
    bool valid;
    {
      mbed::ScopedLock<rtos::Mutex> lock(sensors.mutex);
      valid = sensors.imu.readMotion(sample.motion);
      sample.time = millis();
      sample.sound = soundPower;
      valid = valid && sample.time - audioTime <= 100;
      memcpy(sample.auxiliary, sensors.auxiliary, sizeof(sample.auxiliary));
    }
    for (float value : sample.motion) valid = valid && isfinite(value);
    if (!valid) { acquisitionDrops.fetch_add(1); continue; }
    sample.dropped = acquisitionDrops.load();
    if (!rawQueue.push(sample)) acquisitionDrops.fetch_add(1);
    else processingFlags.set(1);
  }
}

class MotionLag {
 public:
  void reset() { next = count = 0; }
  float update(const RawSample &sample) {
    float result = 0;
    // A fixed 100 ms difference preserves the old 10 Hz acceleration units.
    uint32_t bestDistance = UINT32_MAX, selected = 0;
    for (uint32_t i = 1; i <= count; ++i) {
      uint32_t index = (next + 32 - i) % 32;
      uint32_t age = sample.time - times[index];
      uint32_t distance = age >= 100 ? age - 100 : 100 - age;
      if (distance < bestDistance) { bestDistance = distance; selected = index; }
    }
    if (bestDistance <= 50)
      for (int axis = 0; axis < 3; ++axis) result += fabsf(sample.motion[axis] - axes[selected][axis]);
    times[next] = sample.time;
    memcpy(axes[next], sample.motion, sizeof(axes[next]));
    next = (next + 1) % 32;
    if (count < 32) ++count;
    return result;
  }
 private:
  uint32_t times[32], next = 0, count = 0;
  float axes[32][3];
};

void processSamples() {
  MotionLag motion;
  uint32_t lastSample = 0, lastBaseline = 0;
  bool haveSample = false, haveBaseline = false;
  while (true) {
    processingFlags.wait_any(1);
    RawSample sample;
    while (true) {
      processingIdle.store(false);
      if (!rawQueue.peek(sample)) { processingIdle.store(true); break; }
      rawQueue.consume();
      if (haveSample && sample.time - lastSample > 250) {
        detector.reset(); motion.reset(); haveBaseline = false;
      }
      lastSample = sample.time;
      haveSample = true;
      float accel = motion.update(sample);
      Detection detection;
      if (!haveBaseline || sample.time - lastBaseline >= 100) {
        detection = detector.update(sample.sound, accel);
        lastBaseline = sample.time;
        haveBaseline = true;
      } else detection = detector.evaluate(sample.sound, accel);
      float gyro = sqrtf(sample.motion[3]*sample.motion[3] + sample.motion[4]*sample.motion[4] + sample.motion[5]*sample.motion[5]);
      float features[] = {detection.sound, detection.accel, detection.margin, gyro,
                          sample.auxiliary[0], sample.auxiliary[1], sample.auxiliary[2],
                          sample.auxiliary[3], sample.auxiliary[4]};
      bool complete = detection.ready;
      for (float value : features) complete = complete && isfinite(value);
      float modelScore = -1;
      bool candidate = detection.candidate;
#if HAS_MODEL
      candidate = false;
      if (complete) { modelScore = wearerModel(features); candidate = modelScore >= .6f; }
#endif
      Record record;
      record.seq = sample.seq; record.time = sample.time;
      record.dropped = sample.dropped + processingDrops.load();
      float values[] = {sample.sound, accel, detection.sound, detection.accel, detection.margin,
                        detection.score, modelScore, gyro, features[4], features[5], features[6], features[7], features[8]};
      for (int i = 0; i < 13; ++i) record.values[i] = isfinite(values[i]) ? values[i] : -1;
      record.flags = (detection.ready ? 1 : 0) | (detection.candidate ? 2 : 0) | (candidate ? 4 : 0);
      if (!outputQueue.push(record)) processingDrops.fetch_add(1);
      digitalWrite(LED_BUILTIN, candidate);
      processingIdle.store(true);
    }
  }
}

void reply(const char *text) {
  if (readings.subscribed()) {
    readings.writeValue(reinterpret_cast<const uint8_t *>(text), strlen(text));
    rtos::ThisThread::sleep_for(BLE_PACKET_SPACING_MS);
  }
}

void modelIdentity() {
  char text[64];
  snprintf(text, sizeof(text), "M,%s\n", SPEAKER_MODEL_ID);
  reply(text);
}

void handleCommand(String command) {
  command.trim();
  if (command == "STOP") {
    sampling.store(false);
    sampleTicker.detach();
    sampleFlags.set(1);
    stopping = true;
    return;
  }
  if (command == "STATUS") {
    char text[140];
    snprintf(text, sizeof(text), "STATUS,rate=%u,send_ms=%lu,queued=%lu,raw=%lu,acq_drops=%lu,output_drops=%lu\n",
             sampleRate, static_cast<unsigned long>(sendInterval), static_cast<unsigned long>(outputQueue.size()),
             static_cast<unsigned long>(rawQueue.size()), static_cast<unsigned long>(acquisitionDrops.load()),
             static_cast<unsigned long>(processingDrops.load()));
    reply(text);
    return;
  }
  int split = command.indexOf(' ');
  if (split < 0) { reply("ERROR,command\n"); return; }
  String name = command.substring(0, split);
  const char *argument = command.c_str() + split + 1;
  char *end;
  uint64_t value = strtoull(argument, &end, 10);
  if (!*argument || *end || *argument == '-') { reply("ERROR,value\n"); return; }
  if (name == "CLOCK" && value > 0) {
    char text[80];
    modelIdentity();
    snprintf(text, sizeof(text), "C,%lu,%llu\n", static_cast<unsigned long>(millis()), static_cast<unsigned long long>(value));
    reply(text);
  } else if (name == "SEND" && value <= 600000) {
    sendInterval = value;
    nextSend = millis() + sendInterval;
    reply("OK,SEND\n");
  } else if (name == "RATE" && (value == 10 || value == 50 || value == 100 || value == 200)) {
    sampleTicker.detach();
    if (!sensors.setRate(value)) { reply("ERROR,IMU rate\n"); return; }
    sampleRate = value;
    stopping = false;
    sampling.store(true);
    samplerIdle.store(false);
    pendingTicks.store(0);
    sampleTicker.attach(onSampleTick, std::chrono::microseconds(1000000UL / sampleRate));
    reply("OK,RATE\n");
  } else reply("ERROR,command or range\n");
}

void readCommands() {
  if (!control.written()) return;
  for (int i = 0; i < control.valueLength(); ++i) {
    char value = control.value()[i];
    if (value == '\n') { handleCommand(commandBuffer); commandBuffer = ""; }
    else if (commandBuffer.length() < 63) commandBuffer += value;
    else { commandBuffer = ""; reply("ERROR,command length\n"); }
  }
}

void drainBulk() {
  uint32_t now = millis();
  if (stopping || !sendInterval || static_cast<int32_t>(now - nextSend) >= 0 || outputQueue.size() >= 1152) {
    burstRemaining = outputQueue.size();
    nextSend = now + sendInterval;
  }
  if (!BLE.connected() || !readings.subscribed()) return;
  for (int sent = 0; sent < 4 && burstRemaining; ++sent) {
    uint8_t packet[199] = {4, 1, 0, 0};
    Record record;
    uint8_t count = min(static_cast<uint32_t>(3), burstRemaining);
    for (uint8_t i = 0; i < count; ++i) {
      if (!outputQueue.peek(record, i)) return;
      uint8_t *p = packet + 4 + i * 65;
      memcpy(p, &record.seq, 4); memcpy(p + 4, &record.time, 4); memcpy(p + 8, &record.dropped, 4);
      memcpy(p + 12, record.values, 52); p[64] = record.flags;
    }
    packet[2] = count;
    if (!readings.writeValue(packet, 4 + count * 65)) break;
    outputQueue.consume(count);
    burstRemaining -= count;
    BLE.poll();
    // Yield only the sender; acquisition and inference keep their own cadence.
    rtos::ThisThread::sleep_for(BLE_PACKET_SPACING_MS);
  }
  if (stopping && samplerIdle.load() && !rawQueue.size() && processingIdle.load() && !outputQueue.size()) {
    reply("D\n");
    stopping = false;
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  if (!sensors.begin() || !sensors.setRate(sampleRate) || !BLE.begin()) {
    while (true) { digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN)); delay(200); }
  }
  PDM.onReceive(audioReceived);
  if (!PDM.begin(1, 16000)) {
    while (true) { digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN)); delay(500); }
  }
  BLE.setLocalName("SCI Speaker v2");
  BLE.setConnectionInterval(6, 12);
  BLE.setAdvertisedService(service);
  service.addCharacteristic(readings);
  service.addCharacteristic(control);
  BLE.addService(service);
  BLE.advertise();
  nextSend = millis() + sendInterval;
  acquisitionThread.start(acquire);
  processingThread.start(processSamples);
  sampleTicker.attach(onSampleTick, std::chrono::microseconds(1000000UL / sampleRate));
}

void loop() {
  BLE.poll();
  readCommands();
  sensors.poll(millis());
  drainBulk();
}
