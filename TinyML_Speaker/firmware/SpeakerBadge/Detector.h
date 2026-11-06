#pragma once
#include <math.h>
#include <stdlib.h>

struct Detection {
  float sound = 0, accel = 0, margin = 0, score = 0;
  bool ready = false, candidate = false;
};

class PaperDetector {
 public:
  void reset() { count = next = 0; }
  Detection update(float sound, float accel) {
    Detection result;
    if (!isfinite(sound) || !isfinite(accel) || sound < 0 || accel < 0) {
      reset();
      return result;
    }
    sounds[next] = sound;
    accels[next] = accel;
    next = (next + 1) % 600;
    if (count < 600) ++count;
    if (count < 10) return result;
    for (int i = 0; i < count; ++i) scratch[i] = sounds[i];
    qsort(scratch, count, sizeof(float), compare);
    float lower = quantile(.25f), threshold = quantile(.45f);
    float spread = fmaxf(quantile(.75f) - lower, 1.0f);
    result.sound = (sound - lower) / spread;
    float mean = 0;
    for (int i = 1; i <= 10; ++i) mean += sounds[(next - i + 600) % 600];
    result.margin = (mean / 10 - threshold) / spread;
    for (int i = 0; i < count; ++i) scratch[i] = accels[i];
    qsort(scratch, count, sizeof(float), compare);
    lower = quantile(.25f);
    result.accel = (accel - lower) / fmaxf(quantile(.75f) - lower, 1.0f);
    result.score = result.sound + 1.2f * fminf(fmaxf(result.accel, 0), 2.5f);
    result.candidate = result.score >= .75f && (result.margin > 0 || result.score >= 3.5f);
    result.ready = true;
    return result;
  }

 private:
  float sounds[600], accels[600], scratch[600];
  int count = 0, next = 0;
  static int compare(const void *a, const void *b) {
    float x = *static_cast<const float *>(a), y = *static_cast<const float *>(b);
    return (x > y) - (x < y);
  }
  float quantile(float q) {
    float index = q * (count - 1);
    int low = static_cast<int>(index), high = low + 1 < count ? low + 1 : low;
    return scratch[low] + (index - low) * (scratch[high] - scratch[low]);
  }
};
