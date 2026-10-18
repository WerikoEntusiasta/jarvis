#ifndef WAKE_WORD_ENGINE_H_
#define WAKE_WORD_ENGINE_H_

#include <Arduino.h>
#include <cstdint>
#include <cstddef>

class WakeWordEngine {
 public:
  WakeWordEngine();
  ~WakeWordEngine();

  bool Initialize();
  bool ProcessSamples(const int16_t* samples, size_t num_samples);
  void Reset();

  uint8_t GetLastProbability() const;
  uint8_t GetAverageProbability() const;
  uint8_t GetPeriodMaxProbability() const;
  uint16_t GetLastFeatureMax() const;
  int16_t GetIgnoreWindows() const;
  uint8_t GetThreshold() const;
  void SetThreshold(uint8_t threshold);
  bool IsReady() const;

 private:
  struct Impl;
  Impl* impl_;
};

#endif  // WAKE_WORD_ENGINE_H_
