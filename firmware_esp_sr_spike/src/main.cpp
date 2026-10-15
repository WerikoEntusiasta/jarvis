// SPIKE ESP-SR (POC, SEM flash, SEM serial, SEM alterar firmware_jarvis_custom).
// Objetivo: provar compilacao + mapa de memoria + probe de compatibilidade.
//
// O que este arquivo faz:
//  1. Faz probe de headers reais do ESP-SR via __has_include (nao inclui se ausente).
//  2. Fornece um MOCK com a MESMA FORMA da API real (afe_config_init /
//     esp_afe_handle_from_config / create_from_config + modelo WakeNet wn9_*)
//     para medir o custo do scaffolding no mapa de memoria.
//  3. Imprime via Serial apenas informacoes de versao/ambiente (nao roda AEC real).
//
// IMPORTANTE: este MOCK NAO prova que o ESP-SR linka no Arduino 2.0.17/IDF 4.4.
// Ele prova o baseline de RAM/Flash do board/env + documenta o bloqueio de versao.
// Numeros reais do ESP-SR vêm da documentacao oficial (citada no relatorio).

#include <Arduino.h>

#if __has_include("esp_arduino_version.h")
#include "esp_arduino_version.h"
#endif
#if __has_include("esp_idf_version.h")
#include "esp_idf_version.h"
#endif
#if __has_include("esp_psram.h")
#include "esp_psram.h"
#endif
#if __has_include("esp_chip_info.h")
#include "esp_chip_info.h"
#endif

// ---- Probe do ESP-SR real (somente deteccao, sem incluir se ausente) ----
#if __has_include("esp_afe_sr_iface.h")
#include "esp_afe_sr_iface.h"
#define SPIKE_HAS_REAL_AFE_IFACE 1
#else
#define SPIKE_HAS_REAL_AFE_IFACE 0
#endif

#if __has_include("esp_afe_config.h")
#include "esp_afe_config.h"
#define SPIKE_HAS_REAL_AFE_CONFIG 1
#else
#define SPIKE_HAS_REAL_AFE_CONFIG 0
#endif

#if __has_include("esp_srmodel.h")
#include "esp_srmodel.h"
#define SPIKE_HAS_REAL_SRMODEL 1
#else
#define SPIKE_HAS_REAL_SRMODEL 0
#endif

#if __has_include("model_wn9_hiesp.h") || __has_include("wn9_hiesp.h")
#define SPIKE_HAS_REAL_WN9_MODEL 1
#else
#define SPIKE_HAS_REAL_WN9_MODEL 0
#endif

// ---- MOCK com a mesma FORMA da API real (nomes/assinaturas analogas) ----
// Prefixo spike_ para deixar claro no .map que isto NAO e o ESP-SR real.
namespace esp_sr_spike_mock {

struct FakeModels {
  const char* vad_name = "vadnet1_medium (ref.doc)";
  const char* wakenet_name = "wn9_jarvis_tts (283KB model partition, ref.doc)";
  const char* ns_name = "nsnet2 (ref.doc)";
};

struct FakeAfeConfig {
  const char* input_format;  // ex: "MNR" = Mic + unused + Ref (loopback digital)
  const char* afe_type;      // ex: "AFE_TYPE_SR"
  const char* afe_mode;      // ex: "AFE_MODE_HIGH_PERF"
  FakeModels models;
};

// Assinatura analoga a: afe_config_t *afe_config_init(input_format, models, type, mode)
FakeAfeConfig* spike_afe_config_init(const char* input_format, const FakeModels* models,
                                     const char* afe_type, const char* afe_mode) {
  static FakeAfeConfig cfg;
  cfg.input_format = input_format;
  cfg.afe_type = afe_type;
  cfg.afe_mode = afe_mode;
  if (models) cfg.models = *models;
  return &cfg;
}

struct FakeAfeHandle {
  const char* name = "esp_afe_sr_iface_t (MOCK)";
  int feed_chunksize = 512;  // 32ms @16kHz mono = 512 samples (igual ao doc AFE)
  int feed_channels = 2;     // MNR -> 2 canais alimentados (mic + ref)
  int fetch_chunksize = 512;
};

// Analoga a: esp_afe_handle_from_config(afe_config)
const FakeAfeHandle* spike_afe_handle_from_config(const FakeAfeConfig* /*cfg*/) {
  static FakeAfeHandle h;
  return &h;
}

struct FakeAfeData {
  bool created = true;
};

// Analoga a: afe_handle->create_from_config(afe_config)
FakeAfeData* spike_afe_create_from_config(const FakeAfeHandle* /*h*/, const FakeAfeConfig* /*cfg*/) {
  static FakeAfeData d;
  return &d;
}

}  // namespace esp_sr_spike_mock

static void printLine(const char* s) { Serial.println(s); }

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println(F("==== ESP-SR SPIKE (POC, MOCK API-SHAPE, sem flash) ===="));
#if defined(ESP_ARDUINO_VERSION_MAJOR)
  Serial.printf("Arduino core: %d.%d.%d\n", ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR,
                ESP_ARDUINO_VERSION_PATCH);
#else
  Serial.println(F("Arduino core: desconhecido (macro ausente)"));
#endif
#if defined(ESP_IDF_VERSION_MAJOR)
  Serial.printf("IDF base: %d.%d.%d\n", ESP_IDF_VERSION_MAJOR, ESP_IDF_VERSION_MINOR,
                ESP_IDF_VERSION_PATCH);
#else
  Serial.println(F("IDF base: desconhecido (macro ausente)"));
#endif
  Serial.printf("ESP-SR real presente? afe_iface=%d afe_config=%d srmodel=%d wn9_model=%d\n",
                SPIKE_HAS_REAL_AFE_IFACE, SPIKE_HAS_REAL_AFE_CONFIG, SPIKE_HAS_REAL_SRMODEL,
                SPIKE_HAS_REAL_WN9_MODEL);
  Serial.println(F("ESP-SR requerido: idf>=5.0, component espressif/esp-sr v2.6.0, "
                   "deps esp-dl~3.3.12 + dl_fft + cjson + esp-dsp 1.8.0"));
  Serial.println(F("ESP-SR Arduino: gerar srmodels.bin via movemodel.py + particao 'model' "
                   "(ex: 6000K) + flash manual; ver docs flash_model/README"));

  // Scaffolding com a mesma forma do init real (Steps 1-2 do guia AFE):
  //   models -> afe_config_init("MNR", models, AFE_TYPE_SR, AFE_MODE_HIGH_PERF)
  //   handle -> esp_afe_handle_from_config(cfg) -> create_from_config(cfg)
  // Aqui "MNR" = 1x MIC (ES8311 DIN 10) + 1x N + 1x REF (loopback digital do TX).
  // O AEC NAO recebe referencia por pino; recebe por copia digital do buffer do
  // alto-falante no canal R do feed (channel-interleaved int16 16kHz).
  esp_sr_spike_mock::FakeModels models;  // lista de modelos (MOCK)
  esp_sr_spike_mock::FakeAfeConfig* cfg = esp_sr_spike_mock::spike_afe_config_init(
      "MNR", &models, "AFE_TYPE_SR", "AFE_MODE_HIGH_PERF");
  const esp_sr_spike_mock::FakeAfeHandle* h =
      esp_sr_spike_mock::spike_afe_handle_from_config(cfg);
  esp_sr_spike_mock::FakeAfeData* data = esp_sr_spike_mock::spike_afe_create_from_config(h, cfg);

  Serial.printf("AFE MOCK init: format=%s type=%s mode=%s feed=%d samples x %d ch fetch=%d created=%d\n",
                cfg->input_format, cfg->afe_type, cfg->afe_mode, h->feed_chunksize,
                h->feed_channels, h->fetch_chunksize, (int)data->created);
  Serial.printf("WakeNet MOCK load: model=%s (~291KB medido via GitHub API: wn9_data 289638B)\n",
                cfg->models.wakenet_name);
  Serial.printf("VAD MOCK: %s | NS MOCK: %s\n", cfg->models.vad_name, cfg->models.ns_name);

  Serial.printf("Heap livre (setup): %u bytes | PSRAM: %u bytes\n", (unsigned)ESP.getFreeHeap(),
                (unsigned)ESP.getPsramSize());
  Serial.printf("Flash chip: %u bytes | Sketch free: %u bytes\n", (unsigned)ESP.getFlashChipSize(),
                (unsigned)ESP.getFreeSketchSpace());
  printLine("==== FIM SPIKE (nada foi gravado/flasheado) ====");
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last > 5000) {
    last = millis();
    Serial.printf("[spike] heap=%u psram=%u\n", (unsigned)ESP.getFreeHeap(),
                  (unsigned)ESP.getFreePsram());
  }
  delay(100);
}
