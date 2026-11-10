#pragma once
#include <atomic>
#include <stdint.h>

// Each queue has exactly one producer and one consumer.
template<typename T, uint32_t Capacity> class SpscRing {
  static_assert(Capacity > 1, "A ring needs at least two slots");
 public:
  bool push(const T &value) {
    uint32_t write = written.load(std::memory_order_relaxed);
    uint32_t next = (write + 1) % Capacity;
    if (next == read.load(std::memory_order_acquire)) return false;
    data[write] = value;
    written.store(next, std::memory_order_release);
    return true;
  }
  bool peek(T &value, uint32_t offset = 0) const {
    uint32_t start = read.load(std::memory_order_relaxed);
    uint32_t available = (written.load(std::memory_order_acquire) + Capacity - start) % Capacity;
    if (available <= offset) return false;
    value = data[(start + offset) % Capacity];
    return true;
  }
  void consume(uint32_t count = 1) {
    read.store((read.load(std::memory_order_relaxed) + count) % Capacity, std::memory_order_release);
  }
  uint32_t size() const {
    uint32_t start = read.load(std::memory_order_acquire);
    return (written.load(std::memory_order_acquire) + Capacity - start) % Capacity;
  }
 private:
  T data[Capacity];
  std::atomic<uint32_t> written{0}, read{0};
};
