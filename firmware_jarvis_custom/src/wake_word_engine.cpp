#include "wake_word_engine.h"
#include "hey_jarvis_model_data.h"

#include <frontend.h>
#include <frontend_util.h>

#include <tensorflow/lite/micro/micro_interpreter.h>
#include <tensorflow/lite/micro/micro_mutable_op_resolver.h>
#include <tensorflow/lite/micro/micro_allocator.h>
#include <tensorflow/lite/micro/micro_resource_variable.h>
#include <tensorflow/lite/schema/schema_generated.h>

#include <vector>
#include <algorithm>

constexpr size_t kTensorArenaSize = 36 * 1024;
constexpr size_t kVarArenaSize = 2048;
constexpr size_t kFeatureSize = 40;
constexpr size_t kSlidingWindowSize = 5;
constexpr uint8_t kDefaultCutoffThreshold = 130; // ~0.51 de probabilidade (ajustado p/ responsividade de voz)

struct WakeWordEngine::Impl {
  FrontendState frontend_state{};
  bool frontend_initialized = false;

  uint8_t* tensor_arena = nullptr;
  uint8_t* var_arena = nullptr;
  tflite::MicroAllocator* var_allocator = nullptr;
  tflite::MicroResourceVariables* mrv = nullptr;
  tflite::MicroMutableOpResolver<24> op_resolver;
  const tflite::Model* model = nullptr;
  tflite::MicroInterpreter* interpreter = nullptr;

  uint8_t stride = 3;
  uint8_t current_stride_step = 0;
  int16_t ignore_windows = -10;
  uint8_t cutoff_threshold = kDefaultCutoffThreshold;

  uint8_t last_prob = 0;
  uint8_t last_avg = 0;
  uint8_t period_max = 0;
  uint16_t last_feat_max = 0;

  std::vector<uint8_t> probabilities;
  size_t prob_idx = 0;
  bool model_ready = false;
};

WakeWordEngine::WakeWordEngine() : impl_(new Impl()) {}

WakeWordEngine::~WakeWordEngine() {
  if (impl_) {
    if (impl_->interpreter) {
      delete impl_->interpreter;
    }
    if (impl_->frontend_initialized) {
      FrontendFreeStateContents(&impl_->frontend_state);
    }
    if (impl_->tensor_arena) {
      free(impl_->tensor_arena);
    }
    if (impl_->var_arena) {
      free(impl_->var_arena);
    }
    delete impl_;
  }
}

bool WakeWordEngine::Initialize() {
  Serial.println("[WAKEWORD-LOCAL] Inicializando motor microWakeWord local no ESP32-S3...");

  // 1. Configurar pre-processador frontend oficial microWakeWord
  FrontendConfig config;
  FrontendFillConfigWithDefaults(&config);
  config.window.size_ms = 30;
  config.window.step_size_ms = 10;
  config.filterbank.num_channels = kFeatureSize;
  config.filterbank.lower_band_limit = 125.0f;
  config.filterbank.upper_band_limit = 7500.0f;

  config.noise_reduction.smoothing_bits = 10;
  config.noise_reduction.even_smoothing = 0.025f;
  config.noise_reduction.odd_smoothing = 0.06f;
  config.noise_reduction.min_signal_remaining = 0.05f;

  config.pcan_gain_control.enable_pcan = 1;
  config.pcan_gain_control.strength = 0.95f;
  config.pcan_gain_control.offset = 80.0f;
  config.pcan_gain_control.gain_bits = 21;

  config.log_scale.enable_log = 1;
  config.log_scale.scale_shift = 6;

  if (!FrontendPopulateState(&config, &impl_->frontend_state, 16000)) {
    Serial.println("[WAKEWORD-LOCAL] ERRO ao inicializar FrontendState");
    return false;
  }
  impl_->frontend_initialized = true;

  // 2. Registrar operacoes TFLite Micro para o modelo streaming
  auto& ops = impl_->op_resolver;
  ops.AddCallOnce();
  ops.AddVarHandle();
  ops.AddReshape();
  ops.AddReadVariable();
  ops.AddStridedSlice();
  ops.AddConcatenation();
  ops.AddAssignVariable();
  ops.AddConv2D();
  ops.AddMul();
  ops.AddAdd();
  ops.AddMean();
  ops.AddFullyConnected();
  ops.AddLogistic();
  ops.AddQuantize();
  ops.AddDepthwiseConv2D();
  ops.AddAveragePool2D();
  ops.AddMaxPool2D();
  ops.AddPad();
  ops.AddPack();
  ops.AddSplitV();

  // 3. Alocar arenas de memoria
  impl_->tensor_arena = static_cast<uint8_t*>(heap_caps_malloc(kTensorArenaSize, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!impl_->tensor_arena) {
    impl_->tensor_arena = static_cast<uint8_t*>(malloc(kTensorArenaSize));
  }

  impl_->var_arena = static_cast<uint8_t*>(malloc(kVarArenaSize));
  if (!impl_->tensor_arena || !impl_->var_arena) {
    Serial.println("[WAKEWORD-LOCAL] ERRO ao alocar memoria para arenas TFLite");
    return false;
  }

  impl_->var_allocator = tflite::MicroAllocator::Create(impl_->var_arena, kVarArenaSize);
  impl_->mrv = tflite::MicroResourceVariables::Create(impl_->var_allocator, 20);

  // 4. Carregar modelo TFLite
  impl_->model = tflite::GetModel(g_hey_jarvis_model_data);
  if (impl_->model->version() != TFLITE_SCHEMA_VERSION) {
    Serial.printf("[WAKEWORD-LOCAL] Versao do schema do modelo incompativel: %d\n", impl_->model->version());
    return false;
  }

  impl_->interpreter = new tflite::MicroInterpreter(
      impl_->model, impl_->op_resolver, impl_->tensor_arena, kTensorArenaSize, impl_->mrv);

  if (impl_->interpreter->AllocateTensors() != kTfLiteOk) {
    Serial.println("[WAKEWORD-LOCAL] ERRO ao alocar tensores TFLite");
    return false;
  }

  TfLiteTensor* input = impl_->interpreter->input(0);
  if (input && input->dims && input->dims->size >= 2) {
    impl_->stride = input->dims->data[1];
    Serial.printf("[WAKEWORD-LOCAL] Input: Dims=[%d, %d, %d] Type=%d Stride=%d Scale=%.6f ZeroPoint=%d\n",
                  input->dims->data[0], input->dims->data[1],
                  (input->dims->size >= 3 ? input->dims->data[2] : 0), input->type, impl_->stride,
                  input->params.scale, input->params.zero_point);
  } else {
    impl_->stride = 3;
  }

  size_t num_outputs = impl_->interpreter->outputs_size();
  Serial.printf("[WAKEWORD-LOCAL] Num Outputs: %u\n", (unsigned)num_outputs);
  for (size_t o = 0; o < num_outputs; ++o) {
    TfLiteTensor* ot = impl_->interpreter->output(o);
    if (ot) {
      Serial.printf("[WAKEWORD-LOCAL] Output[%u]: Type=%d Bytes=%u Scale=%.6f ZeroPoint=%d Dims=%d\n",
                    (unsigned)o, ot->type, (unsigned)ot->bytes,
                    ot->params.scale, ot->params.zero_point, ot->dims ? ot->dims->size : 0);
    }
  }

  impl_->probabilities.assign(kSlidingWindowSize, 0);
  impl_->prob_idx = 0;
  impl_->current_stride_step = 0;
  impl_->ignore_windows = -10;
  impl_->cutoff_threshold = kDefaultCutoffThreshold;
  impl_->model_ready = true;

  Serial.println("[WAKEWORD-LOCAL] Motor microWakeWord 'Hey Jarvis' ativado com SUCESSO!");
  return true;
}

void WakeWordEngine::Reset() {
  if (impl_) {
    if (impl_->frontend_initialized) {
      FrontendReset(&impl_->frontend_state);
    }
    std::fill(impl_->probabilities.begin(), impl_->probabilities.end(), 0);
    impl_->prob_idx = 0;
    impl_->current_stride_step = 0;
    impl_->ignore_windows = -10;
    impl_->last_prob = 0;
    impl_->last_avg = 0;
    impl_->period_max = 0;
  }
}

uint8_t WakeWordEngine::GetLastProbability() const {
  return impl_ ? impl_->last_prob : 0;
}

uint8_t WakeWordEngine::GetAverageProbability() const {
  return impl_ ? impl_->last_avg : 0;
}

uint8_t WakeWordEngine::GetPeriodMaxProbability() const {
  return impl_ ? impl_->period_max : 0;
}

uint16_t WakeWordEngine::GetLastFeatureMax() const {
  return impl_ ? impl_->last_feat_max : 0;
}

int16_t WakeWordEngine::GetIgnoreWindows() const {
  return impl_ ? impl_->ignore_windows : -99;
}

uint8_t WakeWordEngine::GetThreshold() const {
  return impl_ ? impl_->cutoff_threshold : kDefaultCutoffThreshold;
}

void WakeWordEngine::SetThreshold(uint8_t threshold) {
  if (impl_) impl_->cutoff_threshold = threshold;
}

bool WakeWordEngine::IsReady() const {
  return impl_ ? impl_->model_ready : false;
}

bool WakeWordEngine::ProcessSamples(const int16_t* samples, size_t num_samples) {
  if (!impl_ || !impl_->model_ready) return false;

  bool wake_detected = false;

  while (num_samples > 0) {
    size_t step_read = 0;
    FrontendOutput fo = FrontendProcessSamples(&impl_->frontend_state, samples, num_samples, &step_read);
    samples += step_read;
    num_samples = (num_samples >= step_read) ? (num_samples - step_read) : 0;

    if (fo.values != nullptr && fo.size == kFeatureSize) {
      TfLiteTensor* input = impl_->interpreter->input(0);
      if (!input || !input->data.int8) continue;

      uint16_t current_fmax = 0;
      for (size_t i = 0; i < kFeatureSize; ++i) {
        if (fo.values[i] > current_fmax) current_fmax = fo.values[i];
      }
      impl_->last_feat_max = current_fmax;

      // 1. Quantizar espectrograma para int8
      int8_t slice_features[kFeatureSize];
      constexpr int32_t value_scale = 256;
      constexpr int32_t value_div = 666;
      for (size_t i = 0; i < kFeatureSize; ++i) {
        int32_t val = ((static_cast<int32_t>(fo.values[i]) * value_scale) + (value_div / 2)) / value_div;
        val += INT8_MIN;
        if (val < -128) val = -128;
        if (val > 127) val = 127;
        slice_features[i] = static_cast<int8_t>(val);
      }

      // 2. Copiar no passo de stride correto
      uint8_t stride = impl_->stride > 0 ? impl_->stride : 1;
      impl_->current_stride_step = impl_->current_stride_step % stride;
      std::memmove(input->data.int8 + (kFeatureSize * impl_->current_stride_step),
                   slice_features, kFeatureSize);
      ++impl_->current_stride_step;

      // 3. Executar inferencia somente quando acumular 'stride' passos
      if (impl_->current_stride_step >= stride) {
        impl_->current_stride_step = 0;

        TfLiteStatus status = impl_->interpreter->Invoke();
        if (status != kTfLiteOk) {
          static unsigned long s_last_inv_err = 0;
          if (millis() - s_last_inv_err > 2000) {
            s_last_inv_err = millis();
            Serial.printf("[WAKE-ERR] Invoke FALHOU! status=%d\n", (int)status);
          }
        } else {
          TfLiteTensor* output = impl_->interpreter->output(0);
          if (output) {
            uint8_t prob = 0;
            if (output->type == kTfLiteFloat32 && output->data.f) {
              float fval = output->data.f[0];
              prob = static_cast<uint8_t>(std::max(0.0f, std::min(255.0f, fval * 255.0f)));
            } else if ((output->type == kTfLiteUInt8 || output->type == 3 || output->bytes == 1) && output->data.uint8) {
              prob = output->data.uint8[0];
            } else if (output->type == kTfLiteInt8 && output->data.int8) {
              int8_t raw = output->data.int8[0];
              if (output->params.scale > 0.0f) {
                float fval = (raw - output->params.zero_point) * output->params.scale;
                prob = static_cast<uint8_t>(std::max(0.0f, std::min(255.0f, fval * 255.0f)));
              } else {
                prob = static_cast<uint8_t>(raw + 128);
              }
            }

            impl_->last_prob = prob;
            if (prob > impl_->period_max) impl_->period_max = prob;

            impl_->probabilities[impl_->prob_idx] = prob;
            impl_->prob_idx = (impl_->prob_idx + 1) % kSlidingWindowSize;

            uint32_t sum = 0;
            uint8_t max_p = 0;
            for (uint8_t p : impl_->probabilities) {
              if (p > max_p) max_p = p;
              sum += p;
            }
            uint8_t avg = sum / kSlidingWindowSize;
            impl_->last_avg = avg;

            static unsigned long s_last_dbg = 0;
            if (millis() - s_last_dbg > 2000) {
              s_last_dbg = millis();
              Serial.printf("[WAKE-LIVE] MaxP=%d/255 | Ult=%d | Med=%d | FeatMax=%u | Ignore=%d\n",
                            impl_->period_max, prob, avg, impl_->last_feat_max, impl_->ignore_windows);
              impl_->period_max = 0;
            }

            if (prob > 25) {
              Serial.printf("[WAKEWORD-LOCAL] Score instantaneo=%d Media=%d (Ignore=%d)\n", prob, avg, impl_->ignore_windows);
            }

            // Resfriamento e warm-up
            if (prob < impl_->cutoff_threshold) {
              impl_->ignore_windows = std::min<int16_t>(impl_->ignore_windows + 1, 0);
            }

            // Detecao da Wake Word ("Hey Jarvis")
            if (impl_->ignore_windows >= 0 && (avg >= 90 || prob >= impl_->cutoff_threshold)) {
              Serial.printf("[WAKEWORD-LOCAL] *** WAKE WORD 'HEY JARVIS' DETECTADA LOCALMENTE! (Prob=%d, Avg=%d) ***\n",
                            prob, avg);
              wake_detected = true;
              std::fill(impl_->probabilities.begin(), impl_->probabilities.end(), 0);
              impl_->ignore_windows = -15; // Cool-off de 15 inferencias (~450ms)
            }
          }
        }
      }
    }

    if (step_read == 0) break;
  }

  return wake_detected;
}
