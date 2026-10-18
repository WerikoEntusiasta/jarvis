/*
 * FIRMWARE PROPRIETÁRIO J.A.R.V.I.S. NÚCLEO, TEMPO, EMOÇÕES & WAKE WORD v10.0
 * Hardware: Esfera Spotpear SP-ESP32-S3-1.28-BOX (GC9A01 LCD + CST816D Touch + ES8311 Audio)
 * 
 * Em conformidade com o Guia de Estilo C++ do Google e ESP-IDF v6.0+ SDK.
 * 
 * Funcionalidades:
 * 1. STANDBY (Brilho 30%): Interface Glass Core com relógio NTP Brasil (UTC-3), clima e estado do nó.
 * 2. ACIONAMENTO POR VOZ: Ao dizer "JARVIS", o núcleo ZimaOS ativa a comunicação e a esfera acende em 100% de brilho com o Rostinho Expressivo Ciano (Feliz/Falando).
 * 3. REAÇÕES / FALA (Brilho 100%): Rostinho Robot Expressivo (Feliz Ciano, Triste Azul, Bravo Vermelho).
 * 4. CANVAS APPROVAL: Cards de aprovação com botões interativos ao toque ([APROVAR] / [CANCELAR]).
 * 5. ÁUDIO BIDIRECIONAL: Codec ES8311 no Barramento I2C 1 (SDA 15, SCL 14) + Barramento I2S (DIN 10, DOUT 8).
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <HTTPClient.h>
#include <WebSocketsClient.h>
#include <LovyanGFX.hpp>
#include <ArduinoJson.h>
#include <Wire.h>
#include <driver/i2s.h>
#include <time.h>
#include <math.h>
#include <ArduinoOTA.h>
#include <HTTPUpdate.h>
#include <WiFiClientSecure.h>
#include <WiFiUdp.h>
#include <mbedtls/md.h>
#include <esp_heap_caps.h>
#include <opus.h>
#include "wake_word_engine.h"

static WakeWordEngine g_wake_word_engine;

#if __has_include("jarvis_sphere_secrets.h")
#include "jarvis_sphere_secrets.h"
#endif
#ifndef JARVIS_SPHERE_DEVICE_TOKEN
#define JARVIS_SPHERE_DEVICE_TOKEN ""
#endif
#ifndef JARVIS_SPHERE_TLS_CA_PEM
#define JARVIS_SPHERE_TLS_CA_PEM ""
#endif
#ifndef JARVIS_SPHERE_SERVER_HOST
#define JARVIS_SPHERE_SERVER_HOST os.environ.get("ZIMA_IP", "127.0.0.1")
#endif
#if __has_include("jarvis_sphere_ca.h")
#include "jarvis_sphere_ca.h"
#undef JARVIS_SPHERE_TLS_CA_PEM
#define JARVIS_SPHERE_TLS_CA_PEM kJarvisSphereTrustedRootPem
#endif


// ============================================================================
// MAPEAMENTO OFICIAL DE PINOS - SPOTPEAR SP-ESP32-S3-1.28-BOX
// ============================================================================
constexpr int kDisplaySpiSclkPin   = 4;
constexpr int kDisplaySpiMosiPin   = 2;
constexpr int kDisplaySpiCsPin     = 5;
constexpr int kDisplaySpiDcPin     = 47;
constexpr int kDisplaySpiResetPin  = 38;
constexpr int kDisplayBacklightPin = 42;

constexpr int kTpSdaPin = 11;
constexpr int kTpSclPin = 7;
constexpr int kTpRstPin = 6;
constexpr int kTpIntPin = 12;

constexpr int kAudioI2sMclkPin  = 16;
constexpr int kAudioI2sBclkPin  = 9;
constexpr int kAudioI2sWsPin    = 45;
constexpr int kAudioI2sDoutPin  = 8;   // Speaker Output
constexpr int kAudioI2sDinPin   = 10;  // Mic Input
constexpr int kAudioCodecSdaPin = 15;
constexpr int kAudioCodecSclPin = 14;
constexpr int kAudioCodecPaPin  = 46; // Power Amplifier Enable
constexpr uint8_t kEs8311I2cAddr = 0x18;

constexpr int kBuiltinLedGpio = 48;
constexpr i2s_port_t kI2sPortNum = I2S_NUM_0;

constexpr int kBatteryAdcPin      = 1;
constexpr int kBatteryChargingPin = 41;

// Configurações de Rede e Servidor J.A.R.V.I.S. Core
#ifdef JARVIS_SPHERE_WIFI_SSID
const char* kDefaultSsid = JARVIS_SPHERE_WIFI_SSID;
const char* kDefaultPass = JARVIS_SPHERE_WIFI_PASS;
#else
const char* kDefaultSsid = "YOUR_WIFI_SSID";
const char* kDefaultPass = "YOUR_WIFI_PASSWORD";
#endif
const char* kZimaOsWsHost = JARVIS_SPHERE_SERVER_HOST;
constexpr int kZimaOsWsPort = 8095;
constexpr int kZimaOsAudioPort = 8096;
const char* kZimaOsWsPath = "/ws";
const char* kSecureFirmwareUrl = "https://" JARVIS_SPHERE_SERVER_HOST ":8096/firmware.bin";

const char* kCatanduvaWeatherApi = "http://api.open-meteo.com/v1/forecast?latitude=-21.1378&longitude=-48.9733&current_weather=true";

// Estados do Display
enum class DisplayMode {
    kStandby,   // Relógio NTP + Temperatura de Catanduva (Brilho 30%)
    kHappy,     // Rostinho Robot Ciano Fofo (Brilho 100%)
    kSpotify,   // Player Spotify (Brilho 100%)
    kTelemetry, // Telemetria em Tempo Real (Brilho 100%)
    kZeDelivery,// Tela Dedicada Permanente do Zé Delivery (Brilho 100%)
    kSad,       // Rostinho Robot Azul Triste (Brilho 100%)
    kAngry,     // Rostinho Robot Vermelho Bravo (Brilho 100%)
    kCard,      // Card Customizado de Aprovação Canvas
    kTimer,     // Contagem Regressiva no Visor Circular
    kAlarm,     // Alarme Programado Disparando
    kVoiceListening,
    kVoiceTranscribing,
    kVoiceSending,
    kVoiceThinking,
    kVoiceQueued,
    kVoiceSuccess,
    kVoiceError
};


class LGFX_JarvisSphere : public lgfx::LGFX_Device {
    lgfx::Panel_GC9A01      panel_instance_;
    lgfx::Bus_SPI           bus_instance_;
    lgfx::Light_PWM         light_instance_;
    lgfx::Touch_CST816S     touch_instance_;

public:
    LGFX_JarvisSphere() {
        {
            auto cfg = bus_instance_.config();
            cfg.spi_host = SPI2_HOST;
            cfg.spi_mode = 0;
            cfg.freq_write = 40000000;
            cfg.pin_sclk = kDisplaySpiSclkPin;
            cfg.pin_mosi = kDisplaySpiMosiPin;
            cfg.pin_miso = -1;
            cfg.pin_dc   = kDisplaySpiDcPin;
            bus_instance_.config(cfg);
            panel_instance_.setBus(&bus_instance_);
        }
        {
            auto cfg = panel_instance_.config();
            cfg.pin_cs           = kDisplaySpiCsPin;
            cfg.pin_rst          = kDisplaySpiResetPin;
            cfg.pin_busy         = -1;
            cfg.panel_width      = 240;
            cfg.panel_height     = 240;
            cfg.offset_x         = 0;
            cfg.offset_y         = 0;
            cfg.invert           = true;
            cfg.rgb_order        = false;
            panel_instance_.config(cfg);
        }
        {
            auto cfg = light_instance_.config();
            cfg.pin_bl = kDisplayBacklightPin;
            cfg.invert = true;
            cfg.freq   = 44100;
            cfg.pwm_channel = 7;
            light_instance_.config(cfg);
            panel_instance_.setLight(&light_instance_);
        }
        {
            auto cfg = touch_instance_.config();
            cfg.x_min = 0;
            cfg.x_max = 239;
            cfg.y_min = 0;
            cfg.y_max = 239;
            cfg.pin_int = kTpIntPin;
            cfg.bus_shared = false;
            cfg.i2c_port = 0;
            cfg.i2c_addr = 0x15;
            cfg.pin_sda = kTpSdaPin;
            cfg.pin_scl = kTpSclPin;
            cfg.freq = 400000;
            touch_instance_.config(cfg);
            panel_instance_.setTouch(&touch_instance_);
        }
        setPanel(&panel_instance_);
    }
};

LGFX_JarvisSphere g_lcd;
LGFX_Sprite g_canvas(&g_lcd);

WebSocketsClient g_web_socket;
// Canal de tela/controles legado (8095) e canal de voz autenticado (WSS 8096).
WebSocketsClient g_audio_web_socket;

// ============================================================================
// CONFIGURAÇÃO OPUS CODEC (16kHz, VOIP, 24kbps, 60ms)
// ============================================================================
constexpr int kOpusSampleRate = 16000;
constexpr int kOpusChannels = 1;
constexpr int kOpusFrameDurationMs = 60;
constexpr int kOpusFrameSamples = (kOpusSampleRate * kOpusFrameDurationMs) / 1000; // 960 amostras (60ms)
constexpr int kOpusPcmBytes = kOpusFrameSamples * sizeof(int16_t); // 1920 bytes

OpusEncoder* g_opus_encoder = nullptr;
int16_t g_opus_pcm_accum[kOpusFrameSamples];
size_t g_opus_pcm_accum_count = 0;
uint8_t g_opus_packet_buf[256];

// Pré-buffer circular de pacotes Opus (8 slots * 60ms = 480ms de histórico)
constexpr size_t kOpusPrerollSlots = 8;
struct OpusPacketSlot {
    uint8_t data[128];
    size_t len;
};
OpusPacketSlot g_opus_preroll_slots[kOpusPrerollSlots];
size_t g_opus_preroll_head = 0;
size_t g_opus_preroll_count = 0;

bool g_mic_speech_active = false;
float g_mic_noise_floor = 180.0f;
uint16_t g_mic_loud_frames = 0;
uint16_t g_mic_silence_frames = 0;

DisplayMode g_current_mode = DisplayMode::kStandby;
unsigned long g_voice_status_until = 0;

// Telemetria em Tempo Real (Direta via UDP local / WebSocket)
int g_telemetry_cpu = 0;
int g_telemetry_ram = 0;
int g_telemetry_gpu_temp = 0;
int g_telemetry_gpu_util = 0;
String g_telemetry_gpu_vram = "0G";

// Zé Delivery Live State (Tela Permanente)
String g_ze_order_number = "897128120";
String g_ze_status = "ENTREGUE!";
String g_ze_items = "Budweiser + Gatorade";
float  g_ze_total = 37.25f;
String g_ze_updated_at = "23:04";

void DrawZeDeliveryScreen();

WiFiUDP g_telemetry_udp;
constexpr int kTelemetryUdpPort = 8888;
bool g_udp_started = false;

void SetDisplayMode(DisplayMode new_mode);

void HandleDirectTelemetryUdp() {
    if (WiFi.status() != WL_CONNECTED) {
        if (g_udp_started) {
            g_telemetry_udp.stop();
            g_udp_started = false;
        }
        return;
    }
    if (!g_udp_started) {
        g_telemetry_udp.begin(kTelemetryUdpPort);
        g_udp_started = true;
        Serial.printf("[UDP TELEMETRY] Escutando na porta UDP %d\n", kTelemetryUdpPort);
    }

    int packet_size = g_telemetry_udp.parsePacket();
    if (packet_size > 0) {
        char packet_buf[512];
        int len = g_telemetry_udp.read(packet_buf, sizeof(packet_buf) - 1);
        if (len > 0) {
            packet_buf[len] = 0;
            JsonDocument doc;
            DeserializationError err = deserializeJson(doc, packet_buf);
            if (!err) {
                if (doc["cpu"].is<int>()) g_telemetry_cpu = doc["cpu"];
                if (doc["ram"].is<int>()) g_telemetry_ram = doc["ram"];
                if (doc["gpu_temp"].is<int>()) g_telemetry_gpu_temp = doc["gpu_temp"];
                if (doc["gpu_util"].is<int>()) g_telemetry_gpu_util = doc["gpu_util"];
                if (doc["gpu_vram"].is<const char*>() || doc["gpu_vram"].is<String>()) {
                    g_telemetry_gpu_vram = doc["gpu_vram"].as<String>();
                }
            }
        }
    }
}



float g_catanduva_temp = 32.0f;
unsigned long g_last_weather_fetch = 0;
unsigned long g_last_wifi_check = 0;
bool g_control_ws_started = false;
bool g_audio_ws_started = false;
bool g_audio_authenticated = false;

// Estado de Toque e Gestos (Swipe vs Tap)
bool g_is_touching = false;
int g_touch_start_x = 0;
int g_touch_start_y = 0;
int g_touch_current_x = 0;
int g_touch_current_y = 0;
unsigned long g_touch_start_time = 0;
unsigned long g_touch_release_time = 0;

int g_blink_counter = 0;
float g_pulse_phase = 0.0f;

// Cartão Customizado (Canvas System)
bool g_is_custom_screen_active = false;
uint32_t g_custom_screen_hold_until = 0;  // card custom segura até interação real/expiração (60s)
String g_current_request_id = "";
String g_current_button1_id = "";
String g_current_button2_id = "";
String g_current_button3_id = "";

// Sistema de Timer Regressivo
bool g_timer_active = false;
bool g_timer_paused = false;
unsigned long g_timer_end_ms = 0;
unsigned long g_timer_pause_remaining_ms = 0;
uint32_t g_timer_total_sec = 0;
String g_timer_label = "TIMER";

// Sistema de Alarme Programado
bool g_alarm_active = false;
int g_alarm_hour = -1;
int g_alarm_minute = -1;
bool g_alarm_ringing = false;
String g_alarm_label = "ALARME";

// Spotify (uso exclusivo da tela Spotify; nenhuma outra tela eh afetada)
String g_spotify_device = "";   // vazio = device padrao do Core
String g_spotify_title = "";
String g_spotify_artist = "";
String g_spotify_art_url = "";
bool g_spotify_playing = false;
bool g_spotify_show_devices = false;
bool g_spotify_show_controls = false;
bool g_spotify_force_refresh = false;

void StartTimer(uint32_t seconds, String label = "TIMER") {
    if (seconds == 0) return;
    g_timer_total_sec = seconds;
    g_timer_end_ms = millis() + (seconds * 1000);
    g_timer_active = true;
    g_timer_paused = false;
    g_timer_label = label;
    SetDisplayMode(DisplayMode::kTimer);
    Serial.printf("[TIMER] Iniciado %d segundos (%s)\n", seconds, label.c_str());
}

void SetAlarm(int hour, int minute, String label = "ALARME") {
    g_alarm_hour = hour;
    g_alarm_minute = minute;
    g_alarm_label = label;
    g_alarm_active = true;
    g_alarm_ringing = false;
    Serial.printf("[ALARME] Programado para %02d:%02d (%s)\n", hour, minute, label.c_str());
}



// Paleta de Cores (Estilo Google C++ Constexpr)
constexpr uint16_t kColorNavyDark   = lgfx::color565(3, 12, 32);
constexpr uint16_t kColorGridLine   = lgfx::color565(8, 28, 60);
constexpr uint16_t kColorGridDot    = lgfx::color565(15, 60, 110);
constexpr uint16_t kColorCyanOuter  = lgfx::color565(0, 80, 180);
constexpr uint16_t kColorCyanMid    = lgfx::color565(0, 170, 240);
constexpr uint16_t kColorCyanNeon   = lgfx::color565(0, 240, 255);
constexpr uint16_t kColorCyanBright = lgfx::color565(180, 250, 255);
constexpr uint16_t kColorBlueSad    = lgfx::color565(40, 130, 250);
constexpr uint16_t kColorRedAngry   = lgfx::color565(255, 30, 40);
constexpr uint16_t kColorRedDark    = lgfx::color565(120, 10, 20);
constexpr uint16_t kColorText       = TFT_WHITE;
constexpr uint16_t kColorBtnConfirm = lgfx::color565(0, 200, 160);
constexpr uint16_t kColorBtnCancel  = lgfx::color565(220, 50, 80);
constexpr uint16_t kColorSpotifyGreen = lgfx::color565(30, 215, 96);

struct BatteryStatus {
    float voltage;
    int percentage;
    bool is_charging;
};

BatteryStatus ReadBatteryStatus() {
    static float s_filtered_vbat = -1.0f;
    static int s_cached_percentage = 0;
    static bool s_cached_charging = false;
    static unsigned long s_last_battery_read = 0;

    // Atualiza a leitura a cada 2000ms para evitar flutuações rápidas
    if (s_filtered_vbat < 0.0f || (millis() - s_last_battery_read > 2000)) {
        s_last_battery_read = millis();

        // Média de 32 amostragens do ADC para filtrar ruído elétrico da ESP32
        uint32_t total_mv = 0;
        constexpr int kSamples = 32;
        for (int i = 0; i < kSamples; ++i) {
            total_mv += analogReadMilliVolts(kBatteryAdcPin);
        }
        float avg_mv = static_cast<float>(total_mv) / static_cast<float>(kSamples);
        float new_vbat = (avg_mv * 2.0f) / 1000.0f;

        if (new_vbat < 0.5f) {
            uint32_t total_raw = 0;
            for (int i = 0; i < kSamples; ++i) {
                total_raw += analogRead(kBatteryAdcPin);
            }
            float avg_raw = static_cast<float>(total_raw) / static_cast<float>(kSamples);
            new_vbat = (avg_raw / 4095.0f) * 3.3f * 2.0f;
        }

        // Filtro Passa-Baixas (Exponential Moving Average)
        if (s_filtered_vbat < 0.0f) {
            s_filtered_vbat = new_vbat;
        } else {
            s_filtered_vbat = (s_filtered_vbat * 0.90f) + (new_vbat * 0.10f);
        }

        int percentage = static_cast<int>((s_filtered_vbat - 3.3f) / (4.2f - 3.3f) * 100.0f);
        if (percentage > 100) percentage = 100;
        if (percentage < 0) percentage = 0;

        s_cached_percentage = percentage;
        s_cached_charging = (digitalRead(kBatteryChargingPin) == LOW);
    }

    return {s_filtered_vbat, s_cached_percentage, s_cached_charging};
}

void SetDisplayMode(DisplayMode new_mode) {
    // TELA CUSTOM ATIVA: status automáticos do núcleo (idle/success/error) NÃO
    // derrubam o card — só interação real de voz, toque em botão ou expiração.
    if (g_is_custom_screen_active) {
        if (millis() < g_custom_screen_hold_until) {
            if (new_mode == DisplayMode::kStandby ||
                new_mode == DisplayMode::kVoiceSuccess ||
                new_mode == DisplayMode::kVoiceError) {
                return;  // mantém o card no ar
            }
        } else {
            g_is_custom_screen_active = false;  // hold expirou
        }
    }
    // Interação de voz real tem prioridade sobre o card (wake/utterance/turno).
    if (new_mode == DisplayMode::kVoiceListening || new_mode == DisplayMode::kVoiceTranscribing ||
        new_mode == DisplayMode::kVoiceSending || new_mode == DisplayMode::kVoiceThinking ||
        new_mode == DisplayMode::kVoiceQueued) {
        g_is_custom_screen_active = false;
        g_custom_screen_hold_until = 0;
    }
    g_current_mode = new_mode;
    if (new_mode == DisplayMode::kSpotify) {
        g_spotify_show_devices = false;
        g_spotify_show_controls = false;
        g_spotify_force_refresh = true;
    }
    if (new_mode == DisplayMode::kVoiceSuccess || new_mode == DisplayMode::kVoiceError) {
        g_voice_status_until = millis() + 5200;
    } else {
        g_voice_status_until = 0;
    }
    if (g_current_mode == DisplayMode::kStandby) {
        g_lcd.setBrightness(77); // 30% de brilho no modo Standby
        g_is_custom_screen_active = false;
    } else {
        g_lcd.setBrightness(255); // 100% de brilho ao interagir/falar
    }
}

void SetVoiceDisplayMode(const String& emotion) {
    if (emotion == "listening") SetDisplayMode(DisplayMode::kVoiceListening);
    else if (emotion == "transcribing") SetDisplayMode(DisplayMode::kVoiceTranscribing);
    else if (emotion == "sending") SetDisplayMode(DisplayMode::kVoiceSending);
    else if (emotion == "thinking" || emotion == "processing") SetDisplayMode(DisplayMode::kVoiceThinking);
    else if (emotion == "queued") SetDisplayMode(DisplayMode::kVoiceQueued);
    else if (emotion == "success" || emotion == "received") SetDisplayMode(DisplayMode::kVoiceSuccess);
    else if (emotion == "error" || emotion == "failed") SetDisplayMode(DisplayMode::kVoiceError);
    else if (emotion == "standby" || emotion == "idle") SetDisplayMode(DisplayMode::kStandby);
    else if (emotion == "happy" || emotion == "speaking") SetDisplayMode(DisplayMode::kHappy);
    else if (emotion == "spotify") SetDisplayMode(DisplayMode::kSpotify);
    else if (emotion == "ze" || emotion == "ze_delivery" || emotion == "delivery") SetDisplayMode(DisplayMode::kZeDelivery);
    else if (emotion == "sad") SetDisplayMode(DisplayMode::kSad);
    else if (emotion == "angry") SetDisplayMode(DisplayMode::kAngry);
}

void InitializeES8311Codec() {
    // 1. Sistema de energia da placa (GPIO 3 = Power enable dos periféricos / amplificador)
    pinMode(3, OUTPUT);
    digitalWrite(3, HIGH);
    delay(15);

    // Amplificador de áudio (PA: GPIO 46)
    pinMode(kAudioCodecPaPin, OUTPUT);
    digitalWrite(kAudioCodecPaPin, HIGH);

    // 2. Barramento I2C 1 (SDA: 15, SCL: 14)
    Wire1.begin(kAudioCodecSdaPin, kAudioCodecSclPin, 400000);
    delay(20);

    auto WriteRegister = [](uint8_t reg, uint8_t val) {
        Wire1.beginTransmission(kEs8311I2cAddr);
        Wire1.write(reg);
        Wire1.write(val);
        Wire1.endTransmission();
    };

    // Sequencia oficial (esp-adf) para 16 kHz, MCLK externo 4.096 MHz, SLAVE, I2S 16-bit.
    // Reset
    WriteRegister(0x00, 0x1F); delay(20);
    WriteRegister(0x00, 0x00);

    // Clock manager
    WriteRegister(0x01, 0x30);
    WriteRegister(0x02, 0x00);
    WriteRegister(0x03, 0x10);
    WriteRegister(0x16, 0x24); // ADC (mic) gain
    WriteRegister(0x04, 0x10);
    WriteRegister(0x05, 0x00);
    WriteRegister(0x0B, 0x00);
    WriteRegister(0x0C, 0x00);
    WriteRegister(0x10, 0x1F);
    WriteRegister(0x11, 0x7F);
    WriteRegister(0x00, 0x80); // Power up

    // Modo SLAVE + MCLK vindo do pino
    WriteRegister(0x00, 0x80);
    WriteRegister(0x01, 0x3F);
    WriteRegister(0x01, 0x3F);

    // Divisores de clock para 16 kHz (MCLK 4.096 MHz)
    WriteRegister(0x02, 0x00);
    WriteRegister(0x05, 0x00);
    WriteRegister(0x03, 0x10);
    WriteRegister(0x04, 0x20);
    WriteRegister(0x07, 0x00);
    WriteRegister(0x08, 0xFF);
    WriteRegister(0x06, 0x03);
    WriteRegister(0x01, 0x3F);
    WriteRegister(0x06, 0x03);

    // Sistema / ADC
    WriteRegister(0x13, 0x10);
    WriteRegister(0x1B, 0x0A);
    WriteRegister(0x1C, 0x6A);

    // Serial Data Port: I2S normal, 16 bits (ADC e DAC) - CRITICO p/ o mic
    WriteRegister(0x09, 0x0C);
    WriteRegister(0x0A, 0x0C);

    // Start (ADC + DAC) e Polarização do Microfone (MIC BIAS 2.5V)
    WriteRegister(0x0E, 0x02); // ADC power up
    WriteRegister(0x12, 0x00);
    WriteRegister(0x14, 0x1F); // ADC PGA Gain (+30dB - Ganho analogico maximo para captura de voz)
    WriteRegister(0x16, 0x24); // ADC digital scale (+24dB oficial)
    WriteRegister(0x17, 0xDF); // ADC digital volume (+16dB para sensibilidade acustica ideal)
    WriteRegister(0x0D, 0x01); // Analog power up
    WriteRegister(0x15, 0x40); // ADC MIC BIAS (Alimenta eletricamente a capsula do microfone)
    WriteRegister(0x37, 0x48); // DAC
    WriteRegister(0x45, 0x00);
    WriteRegister(0x44, 0x50); // Internal power routing

    // Volume do DAC (alto, mas sem estourar: +8 dB)
    WriteRegister(0x32, 0xCF);

    Serial.println("[ES8311] Equalizacao oficial de fabrica Spotpear/Espressif carregada com sucesso!");
}

void InitializeI2SAudio() {
    i2s_config_t i2s_config = {
        .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_RX),
        .sample_rate = 16000,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = 256,
        .use_apll = false,
        .tx_desc_auto_clear = true,
        .fixed_mclk = 0
    };

    i2s_pin_config_t pin_config = {
        .mck_io_num = kAudioI2sMclkPin,  // GPIO 16
        .bck_io_num = kAudioI2sBclkPin,   // GPIO 9
        .ws_io_num = kAudioI2sWsPin,      // GPIO 45
        .data_out_num = kAudioI2sDoutPin, // GPIO 8 (Alto-falante)
        .data_in_num = kAudioI2sDinPin    // GPIO 10 (Microfone)
    };

    i2s_driver_install(kI2sPortNum, &i2s_config, 0, nullptr);
    i2s_set_pin(kI2sPortNum, &pin_config);
    Serial.println("[I2S] Barramento de audio ativado (16 kHz, 16-bit mono)!");
}


void FetchCatanduvaWeather() {
    if (WiFi.status() != WL_CONNECTED) return;
    HTTPClient http;
    http.begin(kCatanduvaWeatherApi);
    http.setTimeout(4000);
    int http_code = http.GET();
    if (http_code == HTTP_CODE_OK) {
        String payload = http.getString();
        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, payload);
        if (!error && doc["current_weather"].is<JsonObject>()) {
            g_catanduva_temp = doc["current_weather"]["temperature"] | g_catanduva_temp;
            Serial.printf("[+] Catanduva Temp: %.1f C\n", g_catanduva_temp);
        }
    }
    http.end();
}

void DrawStandbyClockWeather() {
    // Dashboard executivo compacto, com todos os elementos dentro da área segura circular.
    constexpr uint16_t kDashboardBackground = lgfx::color565(13, 14, 19);
    constexpr uint16_t kDashboardSurface = lgfx::color565(28, 29, 36);
    constexpr uint16_t kDashboardCard = lgfx::color565(38, 39, 47);
    constexpr uint16_t kDashboardBorder = lgfx::color565(57, 58, 67);
    constexpr uint16_t kDashboardText = lgfx::color565(244, 244, 247);
    constexpr uint16_t kDashboardMuted = lgfx::color565(156, 158, 170);
    constexpr uint16_t kDashboardDate = lgfx::color565(187, 190, 204);
    constexpr uint16_t kDashboardOrange = lgfx::color565(255, 98, 39);
    constexpr uint16_t kDashboardGreen = lgfx::color565(43, 211, 151);

    g_canvas.fillScreen(kDashboardBackground);
    g_canvas.fillCircle(120, 120, 107, kDashboardSurface);
    g_canvas.drawCircle(120, 120, 107, kDashboardBorder);

    struct tm timeinfo;
    char time_str[8] = "08:54";
    char date_str[32] = "SAB, 10 JUL";

    if (getLocalTime(&timeinfo)) {
        strftime(time_str, sizeof(time_str), "%H:%M", &timeinfo);
        static const char* const wdays[] = {"DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SAB"};
        static const char* const months[] = {"JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"};
        int w_idx = timeinfo.tm_wday % 7;
        int m_idx = (timeinfo.tm_mon >= 0 && timeinfo.tm_mon < 12) ? timeinfo.tm_mon : 0;
        snprintf(date_str, sizeof(date_str), "%s, %02d %s", wdays[w_idx], timeinfo.tm_mday, months[m_idx]);
    }

    // Relógio e contexto (+5% na hora, -5% na data).
    g_canvas.setTextSize(1.034f);  // +5% adicional (0.985f * 1.05).
    g_canvas.setTextColor(kDashboardText, kDashboardSurface);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(time_str, 120, 79, &fonts::Font6);

    g_canvas.setTextSize(0.797f);  // -5% na data (0.839f * 0.95).
    g_canvas.setTextColor(kDashboardDate, kDashboardSurface);
    g_canvas.drawString(date_str, 120, 116, &fonts::Font4);

    char temp_buf[32];
    snprintf(temp_buf, sizeof(temp_buf), "%.0f C", g_catanduva_temp);
    g_canvas.fillRoundRect(42, 137, 73, 43, 10, kDashboardCard);
    g_canvas.drawRoundRect(42, 137, 73, 43, 10, kDashboardBorder);
    g_canvas.setTextSize(0.55f);
    g_canvas.setTextColor(kDashboardOrange, kDashboardCard);
    g_canvas.setTextDatum(textdatum_t::top_left);
    g_canvas.drawString("CLIMA", 50, 144, &fonts::Font2);
    g_canvas.setTextSize(0.74f);
    g_canvas.setTextColor(kDashboardText, kDashboardCard);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(temp_buf, 78, 164, &fonts::Font4);

    BatteryStatus bat = ReadBatteryStatus();
    char bat_buf[32];
    snprintf(bat_buf, sizeof(bat_buf), "%d%%", bat.percentage);
    g_canvas.fillRoundRect(125, 137, 73, 43, 10, kDashboardCard);
    g_canvas.drawRoundRect(125, 137, 73, 43, 10, kDashboardBorder);
    g_canvas.setTextSize(0.55f);
    g_canvas.setTextColor(kDashboardGreen, kDashboardCard);
    g_canvas.setTextDatum(textdatum_t::top_left);
    g_canvas.drawString("BATERIA", 133, 144, &fonts::Font2);
    g_canvas.setTextSize(0.74f);
    g_canvas.setTextColor(kDashboardText, kDashboardCard);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(bat_buf, 161, 164, &fonts::Font4);

    g_canvas.setTextSize(1.0f);
    g_canvas.pushSprite(0, 0);
}

void DrawRobotFace(DisplayMode mode) {
    g_canvas.fillScreen(kColorNavyDark);

    g_blink_counter++;
    bool is_blinking = (g_blink_counter % 120 > 114);

    if (mode == DisplayMode::kHappy || mode == DisplayMode::kVoiceListening) {
        uint16_t face_color = kColorCyanNeon;
        uint16_t glow_color = kColorCyanBright;

        int left_eye_x = 82, right_eye_x = 158, eye_y = 92, eye_radius = 26;
        
        if (is_blinking) {
            g_canvas.drawArc(left_eye_x, eye_y + 5, 20, 16, 200, 340, face_color);
            g_canvas.drawArc(right_eye_x, eye_y + 5, 20, 16, 200, 340, face_color);
        } else {
            g_canvas.fillCircle(left_eye_x, eye_y, eye_radius, face_color);
            g_canvas.fillCircle(right_eye_x, eye_y, eye_radius, face_color);
            g_canvas.fillCircle(left_eye_x - 7, eye_y - 7, 7, glow_color);
            g_canvas.fillCircle(right_eye_x - 7, eye_y - 7, 7, glow_color);
        }

        int mouth_x = 120, mouth_y = 152;
        g_canvas.fillCircle(mouth_x, mouth_y, 15, face_color);
        g_canvas.fillCircle(mouth_x - 5, mouth_y - 6, 12, kColorNavyDark);
        g_canvas.fillCircle(mouth_x + 5, mouth_y - 6, 12, kColorNavyDark);
        g_canvas.fillCircle(mouth_x, mouth_y + 3, 10, glow_color);

    } else if (mode == DisplayMode::kSad) {
        uint16_t face_color = kColorBlueSad;
        int left_eye_x = 82, right_eye_x = 158, eye_y = 96, eye_radius = 24;

        g_canvas.fillCircle(left_eye_x, eye_y, eye_radius, face_color);
        g_canvas.fillCircle(right_eye_x, eye_y, eye_radius, face_color);
        g_canvas.fillTriangle(left_eye_x - 28, eye_y - 26, left_eye_x + 28, eye_y - 26, left_eye_x + 28, eye_y - 4, kColorNavyDark);
        g_canvas.fillTriangle(right_eye_x - 28, eye_y - 26, right_eye_x + 28, eye_y - 26, right_eye_x - 28, eye_y - 4, kColorNavyDark);

        g_canvas.drawArc(120, 165, 22, 16, 20, 160, face_color);
        g_canvas.drawArc(120, 166, 22, 16, 20, 160, face_color);

    } else if (mode == DisplayMode::kAngry) {
        uint16_t face_color = kColorRedAngry;
        uint16_t glow_color = lgfx::color565(255, 120, 130);

        int left_eye_x = 82, right_eye_x = 158, eye_y = 94, eye_radius = 25;

        g_canvas.drawCircle(120, 120, 118, kColorRedDark);

        g_canvas.fillCircle(left_eye_x, eye_y, eye_radius, face_color);
        g_canvas.fillCircle(right_eye_x, eye_y, eye_radius, face_color);
        g_canvas.fillCircle(left_eye_x + 4, eye_y - 2, 8, glow_color);
        g_canvas.fillCircle(right_eye_x - 4, eye_y - 2, 8, glow_color);

        g_canvas.fillTriangle(left_eye_x - 30, eye_y - 28, left_eye_x + 30, eye_y - 8, left_eye_x - 30, eye_y - 8, kColorNavyDark);
        g_canvas.fillTriangle(right_eye_x + 30, eye_y - 28, right_eye_x - 30, eye_y - 8, right_eye_x + 30, eye_y - 8, kColorNavyDark);

        g_canvas.fillRect(96, 150, 48, 8, face_color);
        g_canvas.fillTriangle(96, 150, 108, 158, 120, 150, kColorNavyDark);
        g_canvas.fillTriangle(120, 150, 132, 158, 144, 150, kColorNavyDark);
    }

    if (mode == DisplayMode::kVoiceListening) {
        const uint8_t pulse = static_cast<uint8_t>((millis() / 130) % 8);
        const uint16_t ring = (pulse < 4) ? kColorCyanBright : kColorCyanNeon;
        g_canvas.drawCircle(120, 120, 112 - (pulse % 3), ring);
        g_canvas.drawCircle(120, 120, 109 - (pulse % 3), lgfx::color565(18, 87, 112));
        const uint16_t pill_color = lgfx::color565(12, 35, 49);
        const uint16_t pulse_color = ((millis() / 350) % 2) ? kColorCyanBright : kColorCyanNeon;
        g_canvas.fillRoundRect(59, 184, 122, 29, 14, pill_color);
        g_canvas.drawCircle(78, 198, 5, pulse_color);
        g_canvas.fillCircle(78, 198, 3, pulse_color);
        g_canvas.setTextSize(0.85f);
        g_canvas.setTextColor(kColorCyanBright, pill_color);
        g_canvas.setTextDatum(textdatum_t::middle_center);
        g_canvas.drawString("OUVINDO", 126, 198, &fonts::Font2);
    }

    g_canvas.pushSprite(0, 0);
}

void DrawVoiceProgressScreen(DisplayMode mode) {
    const uint16_t bg = kColorNavyDark;
    const uint16_t muted = lgfx::color565(104, 132, 155);
    g_canvas.fillScreen(bg);
    g_canvas.drawCircle(120, 120, 116, kColorCyanMid);
    g_canvas.drawCircle(120, 120, 111, lgfx::color565(24, 47, 68));

    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.setTextSize(0.62f);
    g_canvas.setTextColor(kColorCyanBright, bg);
    g_canvas.drawString("J.A.R.V.I.S.", 120, 34, &fonts::Font4);

    const char* line1 = "PROCESSANDO";
    const char* line2 = "NUCLEO";
    const char* footer = "AGUARDE UM INSTANTE";
    uint16_t accent = kColorCyanBright;

    switch (mode) {
        case DisplayMode::kVoiceTranscribing:
            line1 = "ENTENDENDO";
            line2 = "SUA FALA";
            footer = "RECONHECENDO AUDIO";
            break;
        case DisplayMode::kVoiceSending:
            line1 = "ENVIANDO AO";
            line2 = "NUCLEO";
            footer = "PREPARANDO SOLICITACAO";
            break;
        case DisplayMode::kVoiceThinking:
            line1 = "NUCLEO";
            line2 = "PROCESSANDO";
            footer = "AGUARDE A RESPOSTA";
            break;
        case DisplayMode::kVoiceQueued:
            line1 = "AGUARDANDO";
            line2 = "CONEXAO";
            footer = "PEDIDO GUARDADO";
            accent = lgfx::color565(255, 185, 72);
            break;
        case DisplayMode::kVoiceSuccess:
            line1 = "RESPOSTA";
            line2 = "RECEBIDA";
            footer = "JARVIS RESPONDEU";
            accent = kColorCyanBright;
            break;
        case DisplayMode::kVoiceError:
            line1 = "NAO FOI";
            line2 = "ENVIADO";
            footer = "TENTE FALAR NOVAMENTE";
            accent = lgfx::color565(255, 98, 105);
            break;
        default:
            break;
    }

    if (mode == DisplayMode::kVoiceSuccess) {
        g_canvas.drawCircle(120, 91, 35, accent);
        g_canvas.drawLine(102, 91, 115, 104, accent);
        g_canvas.drawLine(115, 104, 140, 77, accent);
        g_canvas.drawLine(103, 91, 116, 104, accent);
        g_canvas.drawLine(116, 104, 141, 77, accent);
    } else if (mode == DisplayMode::kVoiceError) {
        g_canvas.drawCircle(120, 91, 35, accent);
        g_canvas.drawLine(106, 77, 134, 105, accent);
        g_canvas.drawLine(134, 77, 106, 105, accent);
    } else {
        static const int8_t offsets[12][2] = {
            {0, -38}, {19, -33}, {33, -19}, {38, 0}, {33, 19}, {19, 33},
            {0, 38}, {-19, 33}, {-33, 19}, {-38, 0}, {-33, -19}, {-19, -33}
        };
        const int active = (millis() / 90) % 12;
        for (int i = 0; i < 12; ++i) {
            const int trail = (active - i + 12) % 12;
            const uint16_t dot_color = trail == 0 ? kColorCyanBright :
                                       trail < 4 ? kColorCyanNeon : muted;
            g_canvas.fillCircle(120 + offsets[i][0], 91 + offsets[i][1], trail == 0 ? 5 : 3, dot_color);
        }
    }

    g_canvas.setTextSize(0.68f);
    g_canvas.setTextColor(accent, bg);
    g_canvas.drawString(line1, 120, 151, &fonts::Font4);
    g_canvas.drawString(line2, 120, 174, &fonts::Font4);
    g_canvas.setTextSize(0.62f);
    g_canvas.setTextColor(muted, bg);
    g_canvas.drawString(footer, 120, 207, &fonts::Font2);
    g_canvas.pushSprite(0, 0);
}

// ============================================================================
// SPOTIFY (Glass Core, uso exclusivo desta tela)
// Core HTTP:
//   POST http://${ZIMA_IP:-127.0.0.1}:8085/api/spotify/control {action, device}
//     acoes: now_playing, devices (+ transporte via WS, ver abaixo)
//   GET  http://${ZIMA_IP:-127.0.0.1}:8085/api/esfera/cover?url= (proxy JPEG i.scdn.co)
// Transporte (PREV/PLAY/NEXT/VOL) segue via WS `spotify_action` existente,
// apenas com o campo `device` adicionado. Timeouts curtos; falha de rede
// nunca trava o loop: mantem placeholder/texto anterior.
// JPEG decodificado pelo TJpgDec interno do LovyanGFX via g_canvas.drawJpg
// (sem nova dependencia).
// ============================================================================
namespace {
const char* kSpotifyCoreHost = JARVIS_SPHERE_SERVER_HOST;
constexpr int kSpotifyCorePort = 8085;
constexpr unsigned long kSpotifyNpIntervalMs = 8000;
constexpr unsigned long kSpotifyDevStaleMs = 10000;
constexpr size_t kSpotifyCoverMaxBytes = 300UL * 1024UL;
constexpr size_t kSpotifyCoverChunkInit = 64UL * 1024UL;
constexpr int kSpotifyCoverBox = 100;  // capa ~100px centralizada
constexpr int kSpotifyCoverX = (240 - kSpotifyCoverBox) / 2;
constexpr int kSpotifyCoverY = 44;
constexpr int kSpotifyMaxDevices = 5;

unsigned long s_spotify_last_np_ms = 0;
uint8_t* s_spotify_cover_buf = nullptr;
size_t s_spotify_cover_len = 0;
String s_spotify_cover_url = "";
struct SpotifyDeviceInfo {
    String id;
    String name;
    bool active = false;
};
SpotifyDeviceInfo s_spotify_devices[kSpotifyMaxDevices];
int s_spotify_device_count = 0;
unsigned long s_spotify_last_dev_ms = 0;

String SpotifyUrlEncode(const String& s) {
    String out;
    out.reserve(s.length());
    char hex[4];
    for (size_t i = 0; i < s.length(); ++i) {
        const char c = s.charAt(i);
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') {
            out += c;
        } else {
            snprintf(hex, sizeof(hex), "%%%02X", static_cast<unsigned char>(c));
            out += hex;
        }
    }
    return out;
}

bool SpotifyIsScdnUrl(const String& u) {
    return u.startsWith("https://i.scdn.co/");
}

String SpotifyPick(JsonObject obj, const char* k1, const char* k2, const char* k3) {
    if (k1 && !obj[k1].isNull()) return obj[k1].as<String>();
    if (k2 && !obj[k2].isNull()) return obj[k2].as<String>();
    if (k3 && !obj[k3].isNull()) return obj[k3].as<String>();
    return String("");
}

String SpotifyPick(JsonDocument& doc, const char* k1, const char* k2, const char* k3) {
    return SpotifyPick(doc.as<JsonObject>(), k1, k2, k3);
}

String SpotifyShorten(const String& s, size_t max_chars) {
    if (s.length() <= max_chars) return s;
    if (max_chars == 0) return String("");
    return s.substring(0, max_chars - 1) + ".";
}

// Transporte via evento WS existente; apenas adiciona `device`.
void SpotifySendAction(const String& action) {
    if (g_web_socket.isConnected()) {
        JsonDocument doc;
        doc["type"] = "custom";
        doc["payload"]["event"] = "spotify_action";
        doc["payload"]["action"] = action;
        if (g_spotify_device.length() > 0) doc["payload"]["device"] = g_spotify_device;
        String json_str;
        serializeJson(doc, json_str);
        g_web_socket.sendTXT(json_str);
    }
    Serial.printf("[SPOTIFY] Action sent: %s (device=%s)\n",
                  action.c_str(), g_spotify_device.c_str());
}

// POST {action, device} no Core. Preenche `out`; false = falha (chamador usa placeholder).
bool SpotifyHttpControl(const char* action, JsonDocument& out) {
    out.clear();
    if (WiFi.status() != WL_CONNECTED) return false;
    HTTPClient http;
    String url = "http://" + String(kSpotifyCoreHost) + ":" + String(kSpotifyCorePort) +
                 "/api/spotify/control";
    if (!http.begin(url)) return false;
    http.setTimeout(2500);
    http.addHeader("Content-Type", "application/json");
    JsonDocument req;
    req["action"] = action;
    if (g_spotify_device.length() > 0) req["device"] = g_spotify_device;
    String body;
    serializeJson(req, body);
    const int code = http.POST(body);
    bool ok = false;
    if (code == HTTP_CODE_OK) {
        const String payload = http.getString();
        if (payload.length() > 0 && payload.length() < 8192) {
            ok = (deserializeJson(out, payload) == DeserializationError::Ok);
        }
    } else {
        Serial.printf("[SPOTIFY] control(%s) http=%d\n", action, code);
    }
    http.end();
    return ok;
}

void SpotifyFreeCover() {
    if (s_spotify_cover_buf) {
        heap_caps_free(s_spotify_cover_buf);
        s_spotify_cover_buf = nullptr;
    }
    s_spotify_cover_len = 0;
}

// Baixa a capa via proxy do Core e guarda em PSRAM (quando houver).
// Retorna true se ha bytes JPEG validos (magic FF D8) em memoria.
bool SpotifyFetchCover(const String& art_url) {
    SpotifyFreeCover();
    if (!SpotifyIsScdnUrl(art_url)) return false;
    if (WiFi.status() != WL_CONNECTED) return false;
    HTTPClient http;
    const String url = "http://" + String(kSpotifyCoreHost) + ":" + String(kSpotifyCorePort) +
                       "/api/esfera/cover?url=" + SpotifyUrlEncode(art_url);
    if (!http.begin(url)) return false;
    http.setTimeout(4000);
    const int code = http.GET();
    if (code != HTTP_CODE_OK) {
        Serial.printf("[SPOTIFY] cover http=%d\n", code);
        http.end();
        return false;
    }
    const int content_len = http.getSize();  // -1 quando chunked
    if (content_len > static_cast<int>(kSpotifyCoverMaxBytes)) {
        http.end();
        return false;
    }
    size_t capacity = content_len > 0 ? static_cast<size_t>(content_len) : kSpotifyCoverChunkInit;
    uint8_t* buf = static_cast<uint8_t*>(
        heap_caps_malloc(capacity, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!buf) {
        buf = static_cast<uint8_t*>(malloc(capacity));
        if (!buf) {
            http.end();
            return false;
        }
    }
    size_t got = 0;
    WiFiClient* stream = http.getStreamPtr();
    const unsigned long t0 = millis();
    unsigned long last_data = t0;
    bool overflow = false;
    while ((millis() - t0) < 6000) {
        if (got >= kSpotifyCoverMaxBytes) { overflow = true; break; }
        const int avail = stream->available();
        if (avail > 0) {
            if (got + static_cast<size_t>(avail) > capacity) {
                size_t new_cap = capacity * 2;
                while (new_cap < got + static_cast<size_t>(avail)) new_cap *= 2;
                if (new_cap > kSpotifyCoverMaxBytes) { overflow = true; break; }
                uint8_t* bigger = static_cast<uint8_t*>(heap_caps_realloc(
                    buf, new_cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
                if (!bigger) break;
                buf = bigger;
                capacity = new_cap;
            }
            const size_t want = min(static_cast<size_t>(avail), capacity - got);
            const size_t r = stream->readBytes(buf + got, want);
            if (r == 0) break;
            got += r;
            last_data = millis();
            if (content_len > 0 && got >= static_cast<size_t>(content_len)) break;
        } else {
            if (content_len > 0 && got >= static_cast<size_t>(content_len)) break;
            if (!stream->connected()) break;
            if ((millis() - last_data) > 800) break;  // fim do chunked
            delay(5);
        }
    }
    http.end();
    if (overflow || got < 64 || buf[0] != 0xFF || buf[1] != 0xD8) {
        heap_caps_free(buf);
        Serial.println("[SPOTIFY] cover invalida (nao-JPEG/limite)");
        return false;
    }
    s_spotify_cover_buf = buf;
    s_spotify_cover_len = got;
    Serial.printf("[SPOTIFY] cover ok: %u bytes\n", static_cast<unsigned>(got));
    return true;
}

void SpotifyRefreshNowPlaying(bool force) {
    const unsigned long now = millis();
    if (!force && !g_spotify_force_refresh &&
        (now - s_spotify_last_np_ms < kSpotifyNpIntervalMs)) {
        return;
    }
    g_spotify_force_refresh = false;
    s_spotify_last_np_ms = now;
    JsonDocument out;
    if (!SpotifyHttpControl("now_playing", out)) return;  // falha = mantem anterior
    String title = SpotifyPick(out, "title", "track", "name");
    String artist = SpotifyPick(out, "artist", "artists", nullptr);
    String art = SpotifyPick(out, "art_url", "art", "image");
    if (art.isEmpty()) art = SpotifyPick(out, "cover", nullptr, nullptr);
    if (title.isEmpty() && out["item"].is<JsonObject>()) {
        const JsonObject item = out["item"];
        title = SpotifyPick(item, "name", "title", nullptr);
        if (item["artists"].is<JsonArray>() && item["artists"].size() > 0) {
            artist = item["artists"][0]["name"].as<String>();
        }
        if (item["album"].is<JsonObject>()) {
            const JsonObject album = item["album"];
            if (album["images"].is<JsonArray>() && album["images"].size() > 0) {
                art = album["images"][0]["url"].as<String>();
            }
        }
    }
    if (artist.isEmpty() && out["artists"].is<JsonArray>() && out["artists"].size() > 0) {
        JsonVariant first = out["artists"][0];
        artist = first.is<JsonObject>() ? first["name"].as<String>() : first.as<String>();
    }
    if (!out["is_playing"].isNull()) g_spotify_playing = out["is_playing"].as<bool>();
    else if (!out["playing"].isNull()) g_spotify_playing = out["playing"].as<bool>();
    if (title.length() > 0) g_spotify_title = title;
    if (artist.length() > 0) g_spotify_artist = artist;
    // Redesenha/baixa a capa somente quando art_url mudar (cache).
    if (art != s_spotify_cover_url) {
        s_spotify_cover_url = art;
        g_spotify_art_url = art;
        if (art.isEmpty() || !SpotifyIsScdnUrl(art)) {
            SpotifyFreeCover();
        } else {
            SpotifyFetchCover(art);  // falha = placeholder; url segue em cache (sem storm)
        }
    }
}

void SpotifyFetchDevices() {
    JsonDocument out;
    if (!SpotifyHttpControl("devices", out)) return;  // falha = mantem lista anterior
    JsonArray arr;
    if (out["devices"].is<JsonArray>()) {
        arr = out["devices"].as<JsonArray>();
    } else if (out.is<JsonArray>()) {
        arr = out.as<JsonArray>();
    } else {
        return;
    }
    int n = 0;
    for (JsonVariant v : arr) {
        if (n >= kSpotifyMaxDevices) break;
        if (!v.is<JsonObject>()) continue;
        const JsonObject d = v.as<JsonObject>();
        const String id = SpotifyPick(d, "id", "device_id", "name");
        const String nm = SpotifyPick(d, "name", "id", "device_id");
        if (id.isEmpty() && nm.isEmpty()) continue;
        s_spotify_devices[n].id = id.isEmpty() ? nm : id;
        s_spotify_devices[n].name = nm.isEmpty() ? id : nm;
        bool active = false;
        if (!d["is_active"].isNull()) active = d["is_active"].as<bool>();
        else if (!d["active"].isNull()) active = d["active"].as<bool>();
        s_spotify_devices[n].active = active;
        ++n;
    }
    s_spotify_device_count = n;
    s_spotify_last_dev_ms = millis();
    Serial.printf("[SPOTIFY] devices: %d\n", n);
}

template <typename TFont>
void SpotifyDrawCyanButton(int x, int y, int w, int h, const char* label, const TFont* font) {
    g_canvas.fillRoundRect(x, y, w, h, 6, kColorSpotifyGreen);
    g_canvas.drawRoundRect(x, y, w, h, 6, kColorSpotifyGreen);
    g_canvas.setTextColor(TFT_BLACK, kColorSpotifyGreen);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(label, x + w / 2, y + h / 2, font);
}

void SpotifyDrawCoverPlaceholder() {
    // Fundo grafite (mesmo da home); acentos verde Spotify.
    constexpr uint16_t kSpSurface = lgfx::color565(28, 29, 36);
    const int cx = 120;
    const int cy = kSpotifyCoverY + kSpotifyCoverBox / 2;
    g_canvas.fillCircle(cx, cy, 40, lgfx::color565(18, 19, 26));
    g_canvas.drawCircle(cx, cy, 40, kColorSpotifyGreen);
    g_canvas.drawCircle(cx, cy, 28, kColorSpotifyGreen);
    g_canvas.fillCircle(cx, cy, 6, kColorSpotifyGreen);
    g_canvas.setTextColor(kColorSpotifyGreen, kSpSurface);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("SEM CAPA", 120, kSpotifyCoverY + kSpotifyCoverBox - 14, &fonts::Font0);
}

void SpotifyDrawCover() {
    constexpr uint16_t kSpSurface = lgfx::color565(28, 29, 36);
    const int x0 = kSpotifyCoverX;
    const int y0 = kSpotifyCoverY;
    const int s = kSpotifyCoverBox;
    g_canvas.fillRoundRect(x0 - 4, y0 - 4, s + 8, s + 8, 10, kSpSurface);
    if (s_spotify_cover_buf && s_spotify_cover_len > 0) {
        g_canvas.fillRect(x0, y0, s, s, kSpSurface);
        // Tamanho real do JPEG (marcador SOF) para escala e centralização exatas;
        // clip garante que nada escapa da moldura em nenhuma versão da lib.
        int _jw = 0, _jh = 0;
        {
            const uint8_t* _p = s_spotify_cover_buf;
            size_t _n = s_spotify_cover_len;
            for (size_t _i = 0; _i + 9 < _n; ) {
                if (_p[_i] != 0xFF) { _i++; continue; }
                uint8_t _m = _p[_i + 1];
                if (_m == 0xD8 || _m == 0xD9 || (_m >= 0xD0 && _m <= 0xD7)) { _i += 2; continue; }
                if (_i + 9 >= _n) break;
                uint16_t _seg = (uint16_t)(_p[_i + 2] << 8 | _p[_i + 3]);
                if ((_m == 0xC0 || _m == 0xC1 || _m == 0xC2) && _seg >= 7) {
                    _jw = (uint16_t)(_p[_i + 7] << 8 | _p[_i + 8]);
                    _jh = (uint16_t)(_p[_i + 5] << 8 | _p[_i + 6]);
                    break;
                }
                if (_seg < 2) break;
                _i += 2 + _seg;
            }
        }
        float _sc = 1.0f;
        {
            int _mx = _jw > _jh ? _jw : _jh;
            if (_mx > 0) _sc = (float)s / (float)_mx;
        }
        int _dw = _jw > 0 ? (int)(_jw * _sc + 0.5f) : s;
        int _dh = _jh > 0 ? (int)(_jh * _sc + 0.5f) : s;
        g_canvas.setClipRect(x0, y0, s, s);
        const bool ok = g_canvas.drawJpg(s_spotify_cover_buf,
                                         static_cast<uint32_t>(s_spotify_cover_len),
                                         x0 + (s - _dw) / 2, y0 + (s - _dh) / 2, s, s, 0, 0,
                                         _sc, _sc, textdatum_t::top_left);
        g_canvas.clearClipRect();
        if (!ok) SpotifyDrawCoverPlaceholder();
    } else {
        SpotifyDrawCoverPlaceholder();
    }
    g_canvas.drawRoundRect(x0 - 4, y0 - 4, s + 8, s + 8, 10, kColorSpotifyGreen);
    g_canvas.drawRoundRect(x0 - 2, y0 - 2, s + 4, s + 4, 8, kColorSpotifyGreen);
}

// Geometria do overlay de controles (2 col x 3 linhas, botoes grandes p/ dedo).
// Compartilhada entre desenho e toque — manter em sincronia.
constexpr int kSpotifyCtlOX = 24;
constexpr int kSpotifyCtlOY = 40;
constexpr int kSpotifyCtlOW = 192;
constexpr int kSpotifyCtlOH = 172;
constexpr int kSpotifyCtlBW = 82;
constexpr int kSpotifyCtlBH = 38;
constexpr int kSpotifyCtlX0 = 34;
constexpr int kSpotifyCtlX1 = 124;
constexpr int kSpotifyCtlY0 = 66;
constexpr int kSpotifyCtlY1 = 110;
constexpr int kSpotifyCtlY2 = 154;

// Botao CONTROLES da tela principal (unico, largo).
constexpr int kSpotifyMainBtnX = 60;
constexpr int kSpotifyMainBtnY = 178;
constexpr int kSpotifyMainBtnW = 120;
constexpr int kSpotifyMainBtnH = 30;

void DrawSpotifyDevicesOverlay() {
    constexpr uint16_t kOverlayBg = lgfx::color565(6, 20, 40);
    constexpr uint16_t kRowBg = lgfx::color565(10, 34, 56);
    g_canvas.fillRoundRect(28, 52, 184, 160, 12, kOverlayBg);
    g_canvas.drawRoundRect(28, 52, 184, 160, 12, kColorSpotifyGreen);
    g_canvas.setTextColor(kColorSpotifyGreen, kOverlayBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("DISPOSITIVO", 120, 58, &fonts::Font2);
    if (s_spotify_device_count == 0) {
        g_canvas.setTextColor(kColorText, kOverlayBg);
        g_canvas.setTextDatum(textdatum_t::middle_center);
        g_canvas.drawString("SEM DISPOSITIVOS", 120, 120, &fonts::Font2);
        g_canvas.setTextColor(kColorSpotifyGreen, kOverlayBg);
        g_canvas.drawString("TOQUE P/ FECHAR", 120, 150, &fonts::Font2);
        return;
    }
    for (int i = 0; i < s_spotify_device_count; ++i) {
        const int ry = 78 + i * 24;
        const bool selected = (s_spotify_devices[i].id == g_spotify_device) ||
                              (g_spotify_device.isEmpty() && s_spotify_devices[i].active);
        const uint16_t bgc = selected ? kColorSpotifyGreen : kRowBg;
        g_canvas.fillRoundRect(36, ry, 168, 22, 6, bgc);
        if (selected) g_canvas.drawRoundRect(36, ry, 168, 22, 6, kColorSpotifyGreen);
        String nm = SpotifyShorten(s_spotify_devices[i].name, 18);
        if (s_spotify_devices[i].active) nm = "* " + SpotifyShorten(nm, 18);
        g_canvas.setTextColor(selected ? TFT_BLACK : kColorText, bgc);
        g_canvas.setTextDatum(textdatum_t::middle_center);
        g_canvas.drawString(nm.c_str(), 120, ry + 11, &fonts::Font2);
    }
}

// Overlay de controles: ocupa quase toda a tela, 6 botoes grandes (2x3).
void DrawSpotifyControlsOverlay() {
    constexpr uint16_t kCtlBg = lgfx::color565(38, 39, 47);
    g_canvas.fillRoundRect(kSpotifyCtlOX, kSpotifyCtlOY,
                           kSpotifyCtlOW, kSpotifyCtlOH, 14, kCtlBg);
    g_canvas.drawRoundRect(kSpotifyCtlOX, kSpotifyCtlOY,
                           kSpotifyCtlOW, kSpotifyCtlOH, 14, kColorSpotifyGreen);
    g_canvas.setTextColor(kColorSpotifyGreen, kCtlBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("CONTROLES", 120, kSpotifyCtlOY + 6, &fonts::Font2);
    // Linha 0: transporte anterior/proxima.
    SpotifyDrawCyanButton(kSpotifyCtlX0, kSpotifyCtlY0, kSpotifyCtlBW, kSpotifyCtlBH,
                          "PREV", &fonts::Font0);
    SpotifyDrawCyanButton(kSpotifyCtlX1, kSpotifyCtlY0, kSpotifyCtlBW, kSpotifyCtlBH,
                          "NEXT", &fonts::Font0);
    // Linha 1: volume.
    SpotifyDrawCyanButton(kSpotifyCtlX0, kSpotifyCtlY1, kSpotifyCtlBW, kSpotifyCtlBH,
                          "VOL-", &fonts::Font2);
    SpotifyDrawCyanButton(kSpotifyCtlX1, kSpotifyCtlY1, kSpotifyCtlBW, kSpotifyCtlBH,
                          "VOL+", &fonts::Font2);
    // Linha 2: play/pause + dispositivo.
    SpotifyDrawCyanButton(kSpotifyCtlX0, kSpotifyCtlY2, kSpotifyCtlBW, kSpotifyCtlBH,
                          g_spotify_playing ? "PAUSE" : "PLAY", &fonts::Font0);
    SpotifyDrawCyanButton(kSpotifyCtlX1, kSpotifyCtlY2, kSpotifyCtlBW, kSpotifyCtlBH,
                          "DISP", &fonts::Font0);
}

// Retorna true quando o toque foi consumido pela tela Spotify.
bool HandleSpotifyTap(int tx, int ty) {
    if (g_spotify_show_devices) {
        for (int i = 0; i < s_spotify_device_count; ++i) {
            const int ry = 78 + i * 24;
            if (tx >= 36 && tx <= 204 && ty >= ry && ty <= ry + 22) {
                g_spotify_device = s_spotify_devices[i].id;
                g_spotify_show_devices = false;
                g_spotify_show_controls = false;  // selecao fecha tudo e fixa o device
                // Leva o device selecionado ao Core; resposta tolerada/ignorada.
                SpotifySendAction("set_device");
                g_spotify_force_refresh = true;
                Serial.printf("[SPOTIFY] device=%s\n", g_spotify_device.c_str());
                return true;
            }
        }
        g_spotify_show_devices = false;  // toque fora da lista volta ao overlay de controles
        return true;
    }
    if (g_spotify_show_controls) {
        auto in_btn = [tx, ty](int bx, int by) -> bool {
            return tx >= bx && tx <= bx + kSpotifyCtlBW &&
                   ty >= by && ty <= by + kSpotifyCtlBH;
        };
        String action = "";
        if (in_btn(kSpotifyCtlX0, kSpotifyCtlY0)) {
            action = "prev";
        } else if (in_btn(kSpotifyCtlX1, kSpotifyCtlY0)) {
            action = "next";
        } else if (in_btn(kSpotifyCtlX0, kSpotifyCtlY1)) {
            action = "vol_down";
        } else if (in_btn(kSpotifyCtlX1, kSpotifyCtlY1)) {
            action = "vol_up";
        } else if (in_btn(kSpotifyCtlX0, kSpotifyCtlY2)) {
            action = "play_pause";
        } else if (in_btn(kSpotifyCtlX1, kSpotifyCtlY2)) {
            if (WiFi.status() == WL_CONNECTED &&
                (s_spotify_device_count == 0 || (millis() - s_spotify_last_dev_ms > kSpotifyDevStaleMs))) {
                SpotifyFetchDevices();
            }
            g_spotify_show_devices = true;  // abre a lista existente por cima
            return true;
        }
        if (action.length() > 0) {
            SpotifySendAction(action);
            g_spotify_force_refresh = true;  // atualiza faixa/estado apos o comando
            return true;
        }
        g_spotify_show_controls = false;  // toque fora fecha o overlay
        return true;
    }
    if (tx >= kSpotifyMainBtnX && tx <= kSpotifyMainBtnX + kSpotifyMainBtnW &&
        ty >= kSpotifyMainBtnY && ty <= kSpotifyMainBtnY + kSpotifyMainBtnH) {
        g_spotify_show_controls = true;
        return true;
    }
    return false;
}
}  // namespace

void DrawSpotifyScreen() {
    SpotifyRefreshNowPlaying(false);

    // Fundo grafite igual a home (linhas ~540-552): base + circulo + anel.
    constexpr uint16_t kSpBg = lgfx::color565(13, 14, 19);
    constexpr uint16_t kSpSurface = lgfx::color565(28, 29, 36);
    constexpr uint16_t kSpBorder = lgfx::color565(57, 58, 67);
    g_canvas.fillScreen(kSpBg);
    g_canvas.fillCircle(120, 120, 107, kSpSurface);
    g_canvas.drawCircle(120, 120, 107, kSpBorder);

    g_canvas.setTextColor(kColorSpotifyGreen, kSpSurface);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("SPOTIFY", 120, 24, &fonts::Font2);

    SpotifyDrawCover();

    // Nome da musica em destaque, 1-2 linhas, sem artista.
    const String title = g_spotify_title.length() > 0
                             ? g_spotify_title
                             : String("NADA TOCANDO");
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.setTextColor(kColorText, kSpSurface);
    if (title.length() <= 22) {
        g_canvas.drawString(title.c_str(), 120, 152, &fonts::Font2);
    } else {
        // Quebra perto do meio, preferindo espaco, para 2 linhas.
        int split = title.length() / 2;
        int best = -1;
        for (int i = split; i >= 0 && i > split - 12; --i) {
            if (title.charAt(i) == ' ') { best = i; break; }
        }
        if (best < 0) {
            for (size_t i = split; i < title.length() && i < (size_t)(split + 12); ++i) {
                if (title.charAt(i) == ' ') { best = i; break; }
            }
        }
        String l1, l2;
        if (best > 0) {
            l1 = SpotifyShorten(title.substring(0, best), 22);
            l2 = SpotifyShorten(title.substring(best + 1), 22);
        } else {
            l1 = SpotifyShorten(title.substring(0, 22), 22);
            l2 = SpotifyShorten(title.substring(22), 22);
        }
        g_canvas.drawString(l1.c_str(), 120, 148, &fonts::Font2);
        if (l2.length() > 0) g_canvas.drawString(l2.c_str(), 120, 162, &fonts::Font2);
    }

    // Unico botao largo da tela principal.
    SpotifyDrawCyanButton(kSpotifyMainBtnX, kSpotifyMainBtnY,
                          kSpotifyMainBtnW, kSpotifyMainBtnH,
                          "CONTROLES", &fonts::Font2);

    if (g_spotify_show_controls) DrawSpotifyControlsOverlay();
    if (g_spotify_show_devices) DrawSpotifyDevicesOverlay();

    g_canvas.pushSprite(0, 0);
}

void DrawTelemetryScreen() {
    constexpr uint16_t kColorYellowCyber = lgfx::color565(255, 215, 0);
    constexpr uint16_t kColorGrayBg      = lgfx::color565(22, 24, 28);
    constexpr uint16_t kColorCardBg      = lgfx::color565(32, 35, 42);

    g_canvas.fillScreen(kColorGrayBg);

    // Borda Circular Cyberpunk nos 240px
    g_canvas.drawCircle(120, 120, 118, kColorCyanNeon);
    g_canvas.drawCircle(120, 120, 115, kColorYellowCyber);

    // Cabeçalho: "RIG TELEMETRY" compacto no topo (Font2)
    g_canvas.setTextColor(kColorCyanBright, kColorGrayBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("RIG TELEMETRY", 120, 18, &fonts::Font2);

    // Card Central de Telemetria (largura 158px, altura 124px no y=42)
    constexpr int kCardW = 158;
    constexpr int kCardH = 124;
    constexpr int kCardX = (240 - kCardW) / 2;
    constexpr int kCardY = 42;
    g_canvas.fillRoundRect(kCardX, kCardY, kCardW, kCardH, 8, kColorCardBg);
    g_canvas.drawRoundRect(kCardX, kCardY, kCardW, kCardH, 8, lgfx::color565(55, 60, 72));

    // Barras de Progresso Compactas Largura 132px
    constexpr int kBarWidth = 132;
    constexpr int kBarHeight = 8;
    constexpr int kBarX = (240 - kBarWidth) / 2;

    // 1. CPU
    String cpu_str = "CPU: " + String(g_telemetry_cpu) + "%";
    g_canvas.setTextColor(kColorCyanNeon, kColorCardBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(cpu_str.c_str(), 120, kCardY + 6, &fonts::Font2);

    int cpu_bar_y = kCardY + 24;
    g_canvas.drawRoundRect(kBarX, cpu_bar_y, kBarWidth, kBarHeight, 2, kColorCyanMid);
    int cpu_fill = (kBarWidth - 4) * constrain(g_telemetry_cpu, 0, 100) / 100;
    if (cpu_fill > 0) {
        g_canvas.fillRoundRect(kBarX + 2, cpu_bar_y + 2, cpu_fill, kBarHeight - 4, 1, lgfx::color565(0, 220, 255));
    }

    // 2. RAM
    String ram_str = "RAM: " + String(g_telemetry_ram) + "%";
    g_canvas.setTextColor(lgfx::color565(34, 197, 94), kColorCardBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(ram_str.c_str(), 120, kCardY + 36, &fonts::Font2);

    int ram_bar_y = kCardY + 54;
    g_canvas.drawRoundRect(kBarX, ram_bar_y, kBarWidth, kBarHeight, 2, lgfx::color565(40, 120, 70));
    int ram_fill = (kBarWidth - 4) * constrain(g_telemetry_ram, 0, 100) / 100;
    if (ram_fill > 0) {
        g_canvas.fillRoundRect(kBarX + 2, ram_bar_y + 2, ram_fill, kBarHeight - 4, 1, lgfx::color565(34, 197, 94));
    }

    // 3. GPU
    String gpu_str = "GPU: " + String(g_telemetry_gpu_temp) + "C | " + String(g_telemetry_gpu_util) + "%";
    g_canvas.setTextColor(kColorYellowCyber, kColorCardBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(gpu_str.c_str(), 120, kCardY + 66, &fonts::Font2);

    int gpu_bar_y = kCardY + 84;
    g_canvas.drawRoundRect(kBarX, gpu_bar_y, kBarWidth, kBarHeight, 2, lgfx::color565(140, 110, 0));
    int gpu_fill = (kBarWidth - 4) * constrain(g_telemetry_gpu_util, 0, 100) / 100;
    if (gpu_fill > 0) {
        g_canvas.fillRoundRect(kBarX + 2, gpu_bar_y + 2, gpu_fill, kBarHeight - 4, 1, kColorYellowCyber);
    }

    // 4. VRAM Line
    String vram_str = "VRAM: " + g_telemetry_gpu_vram;
    g_canvas.setTextColor(lgfx::color565(200, 220, 255), kColorCardBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(vram_str.c_str(), 120, kCardY + 98, &fonts::Font2);

    // Rodapé limpo
    g_canvas.setTextColor(lgfx::color565(90, 105, 125), kColorGrayBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("[ Toque p/ avancar ]", 120, 184, &fonts::Font0);

    g_canvas.pushSprite(0, 0);
}

void DrawZeDeliveryScreen() {
    constexpr uint16_t kColorZeYellow = lgfx::color565(255, 204, 0);
    constexpr uint16_t kColorZeRed    = lgfx::color565(229, 25, 55);
    constexpr uint16_t kColorDarkBg   = lgfx::color565(18, 18, 22);
    constexpr uint16_t kColorCardBg   = lgfx::color565(28, 30, 36);

    g_canvas.fillScreen(kColorDarkBg);

    // Borda Circular Zé Delivery nos 240px
    g_canvas.drawCircle(120, 120, 118, kColorZeYellow);
    g_canvas.drawCircle(120, 120, 115, kColorZeRed);

    // Cabeçalho: "ZE DELIVERY" compacto e elegante no topo
    g_canvas.setTextColor(kColorZeYellow, kColorDarkBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("ZE DELIVERY", 120, 18, &fonts::Font2);

    // Badge / Status Pill Central
    uint16_t status_bg = kColorZeYellow;
    uint16_t status_text_color = TFT_BLACK;
    String status_upper = g_ze_status;
    status_upper.toUpperCase();

    if (status_upper.indexOf("ENTREGUE") >= 0 || status_upper.indexOf("DELIVERED") >= 0) {
        status_bg = lgfx::color565(34, 197, 94); // Verde Vibrante
        status_text_color = TFT_BLACK;
    } else if (status_upper.indexOf("CAMINHO") >= 0 || status_upper.indexOf("ROUTE") >= 0) {
        status_bg = kColorZeYellow; // Amarelo
        status_text_color = TFT_BLACK;
    } else if (status_upper.indexOf("CANCEL") >= 0) {
        status_bg = kColorZeRed; // Vermelho
        status_text_color = TFT_WHITE;
    } else {
        status_bg = lgfx::color565(59, 130, 246); // Azul Preparando / Recebido
        status_text_color = TFT_WHITE;
    }

    // Badge compacto (largura 124px, altura 20px no y=40)
    constexpr int kBadgeW = 124;
    constexpr int kBadgeH = 20;
    constexpr int kBadgeX = (240 - kBadgeW) / 2;
    constexpr int kBadgeY = 40;
    g_canvas.fillRoundRect(kBadgeX, kBadgeY, kBadgeW, kBadgeH, 5, status_bg);
    g_canvas.drawRoundRect(kBadgeX, kBadgeY, kBadgeW, kBadgeH, 5, TFT_WHITE);
    g_canvas.setTextColor(status_text_color, status_bg);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(g_ze_status.c_str(), 120, kBadgeY + 10, &fonts::Font2);

    // Card de Conteúdo do Pedido (largura 160px, altura 74px no y=66)
    constexpr int kCardW = 160;
    constexpr int kCardH = 74;
    constexpr int kCardX = (240 - kCardW) / 2;
    constexpr int kCardY = 66;
    g_canvas.fillRoundRect(kCardX, kCardY, kCardW, kCardH, 8, kColorCardBg);
    g_canvas.drawRoundRect(kCardX, kCardY, kCardW, kCardH, 8, lgfx::color565(60, 64, 75));

    // Pedido #
    g_canvas.setTextColor(TFT_WHITE, kColorCardBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    String num_str = "PEDIDO #" + g_ze_order_number;
    g_canvas.drawString(num_str.c_str(), 120, kCardY + 6, &fonts::Font2);

    // Itens
    g_canvas.setTextColor(lgfx::color565(200, 220, 240), kColorCardBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    String items_disp = g_ze_items;
    if (items_disp.length() > 20) {
        items_disp = items_disp.substring(0, 18) + "..";
    }
    g_canvas.drawString(items_disp.c_str(), 120, kCardY + 28, &fonts::Font2);

    // Total
    g_canvas.setTextColor(kColorZeYellow, kColorCardBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    char total_buf[32];
    snprintf(total_buf, sizeof(total_buf), "Total: R$ %.2f", g_ze_total);
    g_canvas.drawString(total_buf, 120, kCardY + 50, &fonts::Font2);

    // Botões Inferiores Compactos (largura 64px, altura 28px no y=150)
    // Span total: x=50 a x=190 (140px dentro do circulo)
    // Botão 1: REFRESH
    g_canvas.fillRoundRect(50, 150, 64, 28, 6, kColorZeYellow);
    g_canvas.drawRoundRect(50, 150, 64, 28, 6, TFT_WHITE);
    g_canvas.setTextColor(TFT_BLACK, kColorZeYellow);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString("REFRESH", 82, 164, &fonts::Font2);

    // Botão 2: VOLTAR
    g_canvas.fillRoundRect(126, 150, 64, 28, 6, lgfx::color565(45, 48, 56));
    g_canvas.drawRoundRect(126, 150, 64, 28, 6, lgfx::color565(120, 125, 135));
    g_canvas.setTextColor(TFT_WHITE, lgfx::color565(45, 48, 56));
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString("VOLTAR", 158, 164, &fonts::Font2);

    // Dica de navegação no rodapé curvo
    g_canvas.setTextColor(lgfx::color565(90, 105, 125), kColorDarkBg);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("[ Toque p/ avancar ]", 120, 186, &fonts::Font0);

    g_canvas.pushSprite(0, 0);
}


void RenderCustomScreen(String req_id, String title, String message, String btn1_id, String btn1_label, String btn2_id, String btn2_label, String btn3_id = "", String btn3_label = "") {
    SetDisplayMode(DisplayMode::kCard);
    g_is_custom_screen_active = true;
    g_custom_screen_hold_until = millis() + 60000;  // card segura 60s (idle do núcleo não derruba)
    g_current_request_id = req_id;
    g_current_button1_id = btn1_id;
    g_current_button2_id = btn2_id;
    g_current_button3_id = btn3_id;

    g_canvas.fillScreen(kColorNavyDark);
    g_canvas.drawCircle(120, 120, 118, kColorCyanNeon);
    g_canvas.drawCircle(120, 120, 115, kColorCyanMid);

    g_canvas.setTextColor(kColorCyanBright, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(title.c_str(), 120, 20, &fonts::Font4);

    g_canvas.setTextColor(kColorText, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(message.c_str(), 120, 70, &fonts::Font2);

    if (btn3_label.length() > 0) {
        // Layout de 3 Botões na Base (x: 18..82, 88..152, 158..222 em y=168)
        g_canvas.fillRoundRect(18, 168, 64, 38, 8, kColorBtnConfirm);
        g_canvas.drawRoundRect(18, 168, 64, 38, 8, kColorCyanBright);
        g_canvas.setTextColor(TFT_BLACK, kColorBtnConfirm);
        g_canvas.setTextDatum(textdatum_t::middle_center);
        g_canvas.drawString(btn1_label.c_str(), 50, 187, &fonts::Font2);

        g_canvas.fillRoundRect(88, 168, 64, 38, 8, kColorCyanMid);
        g_canvas.drawRoundRect(88, 168, 64, 38, 8, kColorCyanBright);
        g_canvas.setTextColor(TFT_BLACK, kColorCyanMid);
        g_canvas.setTextDatum(textdatum_t::middle_center);
        g_canvas.drawString(btn2_label.c_str(), 120, 187, &fonts::Font2);

        g_canvas.fillRoundRect(158, 168, 64, 38, 8, kColorBtnCancel);
        g_canvas.drawRoundRect(158, 168, 64, 38, 8, kColorCyanBright);
        g_canvas.setTextColor(kColorText, kColorBtnCancel);
        g_canvas.setTextDatum(textdatum_t::middle_center);
        g_canvas.drawString(btn3_label.c_str(), 190, 187, &fonts::Font2);
    } else {
        // Layout de 2 Botões na Base (x: 35..110 e 130..205 em y=168)
        if (btn1_label.length() > 0) {
            g_canvas.fillRoundRect(35, 168, 75, 38, 8, kColorBtnConfirm);
            g_canvas.drawRoundRect(35, 168, 75, 38, 8, kColorCyanBright);
            g_canvas.setTextColor(TFT_BLACK, kColorBtnConfirm);
            g_canvas.setTextDatum(textdatum_t::middle_center);
            g_canvas.drawString(btn1_label.c_str(), 72, 187, &fonts::Font2);
        }
        if (btn2_label.length() > 0) {
            g_canvas.fillRoundRect(130, 168, 75, 38, 8, kColorBtnCancel);
            g_canvas.drawRoundRect(130, 168, 75, 38, 8, kColorCyanBright);
            g_canvas.setTextColor(kColorText, kColorBtnCancel);
            g_canvas.setTextDatum(textdatum_t::middle_center);
            g_canvas.drawString(btn2_label.c_str(), 167, 187, &fonts::Font2);
        }
    }
    g_canvas.pushSprite(0, 0);
}

void PlayAlarmBeepTone() {
    static unsigned long s_last_beep = 0;
    if (millis() - s_last_beep > 400) {
        s_last_beep = millis();
        int16_t beep_buf[512];
        for (int i = 0; i < 512; i++) {
            float sample = sinf(2.0f * M_PI * 800.0f * i / 16000.0f);
            beep_buf[i] = (int16_t)(sample * 16000.0f);
        }
        size_t written = 0;
        i2s_write(kI2sPortNum, beep_buf, sizeof(beep_buf), &written, 0);
    }
}

void DrawTimerScreen() {
    constexpr uint16_t kColorYellowCyber = lgfx::color565(255, 215, 0);
    g_canvas.fillScreen(kColorNavyDark);

    uint32_t rem_sec = 0;
    if (g_timer_paused) {
        rem_sec = g_timer_pause_remaining_ms / 1000;
    } else if (g_timer_active) {
        long diff = (long)(g_timer_end_ms - millis());
        rem_sec = (diff > 0) ? (diff / 1000) : 0;
    }

    float pct = (g_timer_total_sec > 0) ? ((float)rem_sec / (float)g_timer_total_sec) : 0.0f;
    if (pct > 1.0f) pct = 1.0f;
    if (pct < 0.0f) pct = 0.0f;

    g_canvas.drawCircle(120, 120, 118, kColorGridLine);

    int start_angle = -90;
    int sweep_angle = static_cast<int>(360.0f * pct);
    uint16_t arc_color = (pct > 0.2f) ? kColorCyanNeon : kColorRedAngry;
    g_canvas.drawArc(120, 120, 118, 112, start_angle, start_angle + sweep_angle, arc_color);

    g_canvas.setTextColor(kColorCyanBright, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString("TIMER REGRESSIVO", 120, 18, &fonts::Font4);

    g_canvas.setTextColor(kColorCyanNeon, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(g_timer_label.c_str(), 120, 50, &fonts::Font2);

    int mins = rem_sec / 60;
    int secs = rem_sec % 60;
    char time_buf[16];
    snprintf(time_buf, sizeof(time_buf), "%02d:%02d", mins, secs);

    g_canvas.setTextColor(g_timer_paused ? kColorYellowCyber : kColorCyanBright, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(time_buf, 120, 105, &fonts::Font7);

    if (g_timer_paused) {
        g_canvas.setTextColor(kColorYellowCyber, kColorNavyDark);
        g_canvas.setTextDatum(textdatum_t::top_center);
        g_canvas.drawString("[ PAUSADO ]", 120, 142, &fonts::Font2);
    }

    g_canvas.fillRoundRect(35, 172, 75, 36, 8, g_timer_paused ? kColorBtnConfirm : kColorCyanMid);
    g_canvas.drawRoundRect(35, 172, 75, 36, 8, kColorCyanBright);
    g_canvas.setTextColor(TFT_BLACK, g_timer_paused ? kColorBtnConfirm : kColorCyanMid);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(g_timer_paused ? "RETOMAR" : "PAUSAR", 72, 190, &fonts::Font2);

    g_canvas.fillRoundRect(130, 172, 75, 36, 8, kColorBtnCancel);
    g_canvas.drawRoundRect(130, 172, 75, 36, 8, kColorCyanBright);
    g_canvas.setTextColor(kColorText, kColorBtnCancel);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString("CANCELAR", 167, 190, &fonts::Font2);

    g_canvas.pushSprite(0, 0);
}

void DrawAlarmScreen() {
    g_canvas.fillScreen(kColorNavyDark);

    bool flash = ((millis() / 300) % 2 == 0);
    uint16_t ring_color = flash ? kColorRedAngry : kColorCyanNeon;

    g_canvas.drawCircle(120, 120, 118, ring_color);
    g_canvas.drawCircle(120, 120, 115, ring_color);

    g_canvas.setTextColor(ring_color, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(g_alarm_ringing ? "ALARME TOCANDO!" : "ALARME", 120, 18, &fonts::Font4);

    g_canvas.setTextColor(kColorCyanBright, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(g_alarm_label.c_str(), 120, 50, &fonts::Font2);

    char alarm_time_str[16] = "07:00";
    if (g_alarm_hour >= 0 && g_alarm_minute >= 0) {
        snprintf(alarm_time_str, sizeof(alarm_time_str), "%02d:%02d", g_alarm_hour, g_alarm_minute);
    }

    g_canvas.setTextColor(kColorCyanBright, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString(alarm_time_str, 120, 105, &fonts::Font7);

    g_canvas.fillRoundRect(45, 170, 150, 40, 10, kColorBtnCancel);
    g_canvas.drawRoundRect(45, 170, 150, 40, 10, kColorCyanBright);
    g_canvas.setTextColor(kColorText, kColorBtnCancel);
    g_canvas.setTextDatum(textdatum_t::middle_center);
    g_canvas.drawString("DESLIGAR ALARME", 120, 190, &fonts::Font2);

    g_canvas.pushSprite(0, 0);
}

void DrawOtaProgress(const char* title, int percentage) {

    g_canvas.fillScreen(kColorNavyDark);
    g_canvas.drawCircle(120, 120, 118, kColorCyanNeon);
    g_canvas.drawCircle(120, 120, 116, kColorCyanMid);

    g_canvas.setTextColor(kColorCyanNeon, kColorNavyDark);
    g_canvas.setTextDatum(textdatum_t::top_center);
    g_canvas.drawString(title, 120, 45, &fonts::Font4);

    if (percentage >= 0) {
        char percent_buf[16];
        snprintf(percent_buf, sizeof(percent_buf), "%d%%", percentage);

        g_canvas.setTextColor(kColorCyanBright, kColorNavyDark);
        g_canvas.setTextDatum(textdatum_t::middle_center);
        g_canvas.drawString(percent_buf, 120, 110, &fonts::Font6);

        constexpr int kBarWidth = 160;
        constexpr int kBarHeight = 16;
        constexpr int kBarX = (240 - kBarWidth) / 2;
        constexpr int kBarY = 160;

        g_canvas.drawRoundRect(kBarX, kBarY, kBarWidth, kBarHeight, 4, kColorCyanMid);
        int fill_width = (kBarWidth - 4) * percentage / 100;
        if (fill_width > 0) {
            g_canvas.fillRoundRect(kBarX + 2, kBarY + 2, fill_width, kBarHeight - 4, 2, kColorCyanNeon);
        }
    }

    g_canvas.pushSprite(0, 0);
}

void SetupArduinoOta() {
    ArduinoOTA.setHostname("jarvis-sphere-esp32s3");

    ArduinoOTA.onStart([]() {
        String type;
        if (ArduinoOTA.getCommand() == U_FLASH) {
            type = "sketch";
        } else {
            type = "filesystem";
        }
        Serial.println("[OTA] Inicio da atualizacao ArduinoOTA: " + type);
        DrawOtaProgress("ATUALIZANDO OTA...", 0);
    });

    ArduinoOTA.onEnd([]() {
        Serial.println("\n[OTA] Atualizacao ArduinoOTA Concluida!");
        DrawOtaProgress("ATUALIZANDO OTA...", 100);
    });

    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        int percentage = static_cast<int>(progress / (total / 100));
        Serial.printf("[OTA] Progresso: %d%%\r", percentage);
        DrawOtaProgress("ATUALIZANDO OTA...", percentage);
    });

    ArduinoOTA.onError([](ota_error_t error) {
        Serial.printf("[OTA] Erro [%u]\n", error);
        DrawOtaProgress("ERRO NO OTA", -1);
    });

    ArduinoOTA.begin();
    Serial.println("[+] ArduinoOTA configurado e iniciado! Hostname: jarvis-sphere-esp32s3");
}

class JarvisPinnedWiFiClientSecure final : public WiFiClientSecure {
public:
    int connect(const char* host, uint16_t port, int32_t timeout) override {
        // TLS is established first, then the exact server certificate and host
        // are checked before HTTPClient can send the OTA token or request.
        setInsecure();
        const int connected = WiFiClientSecure::connect(host, port, timeout);
        if (connected <= 0) return connected;
        if (!verify(kJarvisSphereServerSha256Fingerprint, host)) {
            Serial.println("[OTA] Certificado remoto nao confere com o pin fixado.");
            stop();
            return 0;
        }
        return connected;
    }

    int connect(IPAddress ip, uint16_t port, int32_t timeout) override {
        const String host = ip.toString();
        return connect(host.c_str(), port, timeout);
    }
};

void ExecuteHttpOtaUpdate(const String& url) {
    String target_url = url;
    if (target_url.length() == 0 || target_url.indexOf("://") < 0) {
        target_url = "http://" + String(JARVIS_SPHERE_SERVER_HOST) + ":8095/firmware.bin";
    }

    Serial.printf("[OTA] Iniciando HTTP OTA Update via URL: %s\n", target_url.c_str());
    DrawOtaProgress("ATUALIZANDO VIA WI-FI...", 0);

    httpUpdate.onStart([]() {
        Serial.println("[OTA] HTTP OTA Iniciado.");
        DrawOtaProgress("ATUALIZANDO VIA WI-FI...", 0);
    });

    httpUpdate.onEnd([]() {
        Serial.println("[OTA] HTTP OTA Concluido com Sucesso.");
        DrawOtaProgress("ATUALIZANDO VIA WI-FI...", 100);
    });

    httpUpdate.onProgress([](int current, int total) {
        if (total > 0) {
            int percentage = (current * 100) / total;
            Serial.printf("[OTA] HTTP OTA Progresso: %d%%\r", percentage);
            DrawOtaProgress("ATUALIZANDO VIA WI-FI...", percentage);
        }
    });

    httpUpdate.onError([](int error_code) {
        Serial.printf("[OTA] HTTP OTA Erro [%d]: %s\n", error_code, httpUpdate.getLastErrorString().c_str());
        DrawOtaProgress("ERRO NO OTA", -1);
    });

    httpUpdate.rebootOnUpdate(true);

    t_httpUpdate_return ret;
    if (target_url.startsWith("https://")) {
        WiFiClientSecure secure_client;
        secure_client.setInsecure();
        const HTTPUpdateRequestCB add_ota_auth = [](HTTPClient* http) {
            if (!http) return;
            http->addHeader("X-Jarvis-Device", "jarvis_sphere_esp32s3");
            String auth = "Bearer ";
            auth += JARVIS_SPHERE_DEVICE_TOKEN;
            http->addHeader("Authorization", auth);
        };
        ret = httpUpdate.update(secure_client, target_url, "", add_ota_auth);
    } else {
        WiFiClient wifi_client;
        ret = httpUpdate.update(wifi_client, target_url);
    }

    switch (ret) {
        case HTTP_UPDATE_FAILED:
            Serial.printf("[OTA] HTTPUpdate Falhou! Erro (%d): %s\n", httpUpdate.getLastError(), httpUpdate.getLastErrorString().c_str());
            DrawOtaProgress("FALHA NO OTA", -1);
            delay(2500);
            SetDisplayMode(DisplayMode::kStandby);
            break;
        case HTTP_UPDATE_NO_UPDATES:
            Serial.println("[OTA] HTTPUpdate: Sem atualizacoes disponiveis.");
            SetDisplayMode(DisplayMode::kStandby);
            break;
        case HTTP_UPDATE_OK:
            Serial.println("[OTA] HTTPUpdate Sucesso! Reiniciando...");
            break;
    }
}

// Ringbuffer de playback TTS de 512 KB alocado na PSRAM (sem consumir SRAM interna)
constexpr size_t kTtsRingBufferSize = 512 * 1024;
static uint8_t* g_tts_ringbuffer = nullptr;
static volatile size_t g_tts_rb_head = 0;
static volatile size_t g_tts_rb_tail = 0;
static volatile size_t g_tts_rb_count = 0;
static portMUX_TYPE g_tts_mux = portMUX_INITIALIZER_UNLOCKED;
static unsigned long g_last_tts_time = 0;
static unsigned long g_last_tts_play_ms = 0;

void PlayWakeBeep() {
    static unsigned long s_last_wake_beep = 0;
    if (millis() - s_last_wake_beep < 3000) {
        return; // Previne bips múltiplos simultâneos se houver pacotes repetidos
    }
    s_last_wake_beep = millis();

    // Dois tons curtos dão retorno imediato sem gerar um buffer grande no ESP32.
    int16_t samples[320];
    const uint16_t frequencies[] = {660, 880};
    for (uint16_t frequency : frequencies) {
        for (size_t i = 0; i < 320; ++i) {
            const float envelope = (i < 24) ? (static_cast<float>(i) / 24.0f) :
                                  (i > 270 ? static_cast<float>(319 - i) / 49.0f : 1.0f);
            samples[i] = static_cast<int16_t>(sinf(2.0f * PI * frequency * i / 16000.0f) * 9000.0f * envelope);
        }
        size_t written = 0;
        i2s_write(kI2sPortNum, samples, sizeof(samples), &written, portMAX_DELAY);
    }
    g_last_tts_time = millis();
}

bool SendSphereAuthProof(WebSocketsClient& socket, const String& nonce) {
    const char* secret = JARVIS_SPHERE_DEVICE_TOKEN;
    if (!secret || strlen(secret) < 32 || nonce.length() < 32) return false;

    const String device_id = "jarvis_sphere_esp32s3";
    String material = "jarvis-sphere-v1:";
    material += device_id;
    material += ':';
    material += nonce;
    const mbedtls_md_info_t* md_info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!md_info) return false;

    uint8_t digest[32];
    if (mbedtls_md_hmac(md_info, reinterpret_cast<const unsigned char*>(secret), strlen(secret),
                        reinterpret_cast<const unsigned char*>(material.c_str()), material.length(), digest) != 0) {
        return false;
    }
    char proof[65];
    for (size_t i = 0; i < sizeof(digest); ++i) snprintf(proof + i * 2, 3, "%02x", digest[i]);
    proof[64] = '\0';

    JsonDocument auth_doc;
    auth_doc["type"] = "auth";
    auth_doc["device_id"] = device_id;
    auth_doc["proof"] = proof;
    String auth_json;
    serializeJson(auth_doc, auth_json);
    return socket.sendTXT(auth_json);
}

void ResetMicSpeechGate() {
    g_mic_speech_active = false;
    g_mic_loud_frames = 0;
    g_mic_silence_frames = 0;
    g_opus_preroll_head = 0;
    g_opus_preroll_count = 0;
    g_opus_pcm_accum_count = 0;
}

void InitializeOpusEncoder() {
    int error = 0;
    g_opus_encoder = opus_encoder_create(kOpusSampleRate, kOpusChannels, OPUS_APPLICATION_VOIP, &error);
    if (error != OPUS_OK || g_opus_encoder == nullptr) {
        Serial.printf("[OPUS] Falha ao instanciar encoder Opus: erro %d\n", error);
        return;
    }
    opus_encoder_ctl(g_opus_encoder, OPUS_SET_BITRATE(24000)); // 24 kbps VOIP
    opus_encoder_ctl(g_opus_encoder, OPUS_SET_COMPLEXITY(3));  // Equilíbrio ideal CPU/qualidade ESP32-S3
    opus_encoder_ctl(g_opus_encoder, OPUS_SET_SIGNAL(OPUS_SIGNAL_VOICE));
    Serial.println("[OPUS] Encoder Opus inicializado com sucesso (16kHz, VOIP, 24kbps, 60ms)!");
}

void PushOpusPreroll(const uint8_t* data, size_t len) {
    if (len > sizeof(g_opus_preroll_slots[0].data)) return;
    memcpy(g_opus_preroll_slots[g_opus_preroll_head].data, data, len);
    g_opus_preroll_slots[g_opus_preroll_head].len = len;
    g_opus_preroll_head = (g_opus_preroll_head + 1) % kOpusPrerollSlots;
    if (g_opus_preroll_count < kOpusPrerollSlots) {
        g_opus_preroll_count++;
    }
}

void FlushOpusPreroll() {
    WebSocketsClient& sock = (g_audio_web_socket.isConnected() && g_audio_authenticated) ? g_audio_web_socket : g_web_socket;
    if (!sock.isConnected() || g_opus_preroll_count == 0) return;
    const size_t start = (g_opus_preroll_head + kOpusPrerollSlots - g_opus_preroll_count) % kOpusPrerollSlots;
    for (size_t i = 0; i < g_opus_preroll_count; ++i) {
        const size_t idx = (start + i) % kOpusPrerollSlots;
        if (g_opus_preroll_slots[idx].len > 0) {
            sock.sendBIN(g_opus_preroll_slots[idx].data, g_opus_preroll_slots[idx].len);
        }
    }
    g_opus_preroll_count = 0;
}

// ============================================================================
// DIAG WS (somente metadados; nunca segredo, nonce, proof ou áudio)
// ============================================================================
namespace {
uint32_t s_ws_connects = 0;
uint32_t s_ws_drops = 0;
uint32_t s_ws_auth_fail = 0;
String DiagTs() {
    struct tm t;
    char b[32];
    if (getLocalTime(&t, 2)) {
        strftime(b, sizeof(b), "%H:%M:%S", &t);
        return String(b);
    }
    return String(millis());
}
void LogWs(const char* chan, const char* ev, const String& detail = "") {
    Serial.printf("[DIAG][%s][%s][ts=%s][ms=%lu][heap=%u][rssi=%d][c=%lu][d=%lu] %s\n",
                  chan, ev, DiagTs().c_str(), millis(),
                  (unsigned)ESP.getFreeHeap(), WiFi.RSSI(),
                  (unsigned long)s_ws_connects, (unsigned long)s_ws_drops,
                  detail.c_str());
}
}  // namespace

void ProcessWebSocketEvent(WebSocketsClient& socket, bool audio_channel,
                           WStype_t type, uint8_t* payload, size_t length) {
    if (type == WStype_CONNECTED) {
        Serial.println("[+] WebSocket conectado ao ZimaOS Xiaozhi Server!");
        s_ws_connects++;
        LogWs(audio_channel ? "VOZ" : "CTRL", "CONNECTED", "hello-sent");
        JsonDocument hello_doc;
        hello_doc["type"] = "hello";
        hello_doc["device"] = "jarvis_sphere_esp32s3";
        hello_doc["device_id"] = "jarvis_sphere_esp32s3";
        hello_doc["version"] = 1;
        hello_doc["transport"] = "websocket";
        JsonObject audio_params = hello_doc["audio_params"].to<JsonObject>();
        audio_params["format"] = "opus";
        audio_params["sample_rate"] = 16000;
        audio_params["channels"] = 1;
        audio_params["frame_duration"] = 60;
        String hello_str;
        serializeJson(hello_doc, hello_str);
        socket.sendTXT(hello_str);
        Serial.println("[+] Handshake 'hello' enviado ao Xiaozhi Server!");
    } else if (type == WStype_TEXT) {
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, payload);
        if (err) return;

        String msg_type = doc["type"] | "";
        
        // Acionamento por Voz / Wake Word / Emoção
        if (msg_type == "wakeup") {
            PlayWakeBeep();
            SetDisplayMode(DisplayMode::kVoiceListening);
        }
        else if (msg_type == "jarvis.status") {
            String state = doc["state"] | "idle";
            SetVoiceDisplayMode(state);
        }
        else if (msg_type == "challenge") {
            String nonce = doc["nonce"] | "";
            LogWs(audio_channel ? "VOZ" : "CTRL", "CHALLENGE", "nonce-len=" + String(nonce.length()));
            if (!SendSphereAuthProof(socket, nonce)) {
                Serial.println("[WSS] Prova do dispositivo não enviada; confira o segredo local.");
                SetDisplayMode(DisplayMode::kVoiceError);
            }
        }
        else if (msg_type == "auth_error") {
            Serial.println("[WSS] Dispositivo recusado pelo servidor.");
            s_ws_auth_fail++;
            LogWs(audio_channel ? "VOZ" : "CTRL", "AUTH_FAIL", "");
            SetDisplayMode(DisplayMode::kVoiceError);
        }
        else if (msg_type == "hello") {
            if (audio_channel) {
                g_audio_authenticated = true;
                Serial.println("[WSS] Canal de voz AUTENTICADO com sucesso!");
            }
            SetDisplayMode(DisplayMode::kStandby);
        }
        else if (msg_type == "stt") {
            SetDisplayMode(DisplayMode::kVoiceThinking);
        }
        else if (msg_type == "emotion") {
            String emo = doc["emotion"] | "happy";
            SetVoiceDisplayMode(emo);
        }
        else if (msg_type == "tts" || msg_type == "speaking") {
            String state = doc["state"] | "start";
            if (state == "start" || state == "speaking") {
                SetDisplayMode(DisplayMode::kHappy);
            }
            // Quando receber "stop", não força Standby imediato: permite o speaker terminar a drenagem do áudio.
        }
        else if (msg_type == "jarvis.ota_update") {
            String ota_url = doc["url"] | doc["payload"]["url"] | "";
            if (ota_url.length() > 0) {
                ExecuteHttpOtaUpdate(ota_url);
            }
        }
        else if (msg_type == "jarvis.telemetry") {
            JsonObject payload_obj = doc["payload"].is<JsonObject>() ? doc["payload"] : doc.as<JsonObject>();
            g_telemetry_cpu = payload_obj["cpu"] | g_telemetry_cpu;
            g_telemetry_ram = payload_obj["ram"] | g_telemetry_ram;
            g_telemetry_gpu_temp = payload_obj["gpu_temp"] | g_telemetry_gpu_temp;
            g_telemetry_gpu_util = payload_obj["gpu_util"] | g_telemetry_gpu_util;
            if (payload_obj["gpu_vram"].is<const char*>() || payload_obj["gpu_vram"].is<String>()) {
                g_telemetry_gpu_vram = payload_obj["gpu_vram"].as<String>();
            }
        }
        else if (msg_type == "jarvis.ze_status" || msg_type == "ze_delivery") {
            JsonObject p = doc["payload"].is<JsonObject>() ? doc["payload"] : doc.as<JsonObject>();
            if (p["number"].is<const char*>() || p["number"].is<String>()) g_ze_order_number = p["number"].as<String>();
            if (p["status"].is<const char*>() || p["status"].is<String>()) g_ze_status = p["status"].as<String>();
            if (p["items"].is<const char*>() || p["items"].is<String>()) g_ze_items = p["items"].as<String>();
            if (p["total"].is<float>() || p["total"].is<int>()) g_ze_total = p["total"].as<float>();
            if (p["updated_at"].is<const char*>() || p["updated_at"].is<String>()) g_ze_updated_at = p["updated_at"].as<String>();
            bool show = p["show"] | true;
            if (show) SetDisplayMode(DisplayMode::kZeDelivery);
        }
        else if (msg_type == "custom") {
            String event = doc["payload"]["event"] | doc["event"] | "";
            if (event == "jarvis.emotion") {
                String emo = doc["payload"]["emotion"] | doc["emotion"] | "happy";
                SetVoiceDisplayMode(emo);
            }
            else if (event == "jarvis.telemetry") {
                JsonObject payload_obj = doc["payload"].is<JsonObject>() ? doc["payload"] : doc.as<JsonObject>();
                g_telemetry_cpu = payload_obj["cpu"] | g_telemetry_cpu;
                g_telemetry_ram = payload_obj["ram"] | g_telemetry_ram;
                g_telemetry_gpu_temp = payload_obj["gpu_temp"] | g_telemetry_gpu_temp;
                g_telemetry_gpu_util = payload_obj["gpu_util"] | g_telemetry_gpu_util;
                if (payload_obj["gpu_vram"].is<const char*>() || payload_obj["gpu_vram"].is<String>()) {
                    g_telemetry_gpu_vram = payload_obj["gpu_vram"].as<String>();
                }
            }

            else if (event == "jarvis.ota_update") {
                String ota_url = doc["payload"]["url"] | doc["url"] | "";
                if (ota_url.length() > 0) {
                    ExecuteHttpOtaUpdate(ota_url);
                }
            }
            else if (event == "jarvis.show_screen") {
                String req_id = doc["payload"]["request_id"] | "";
                JsonObject screen = doc["payload"]["screen"];
                String title = screen["title"] | "J.A.R.V.I.S.";
                String message = screen["message"] | "";
                String btn1_id = screen["button1_id"] | "";
                String btn1_label = screen["button1_label"] | "";
                String btn2_id = screen["button2_id"] | "";
                String btn2_label = screen["button2_label"] | "";
                String btn3_id = screen["button3_id"] | "";
                String btn3_label = screen["button3_label"] | "";
                RenderCustomScreen(req_id, title, message, btn1_id, btn1_label, btn2_id, btn2_label, btn3_id, btn3_label);
            }
            else if (event == "jarvis.timer" || msg_type == "jarvis.timer") {
                JsonObject p = doc["payload"].is<JsonObject>() ? doc["payload"] : doc.as<JsonObject>();
                uint32_t secs = p["seconds"] | p["sec"] | 0;
                uint32_t mins = p["minutes"] | p["min"] | 0;
                uint32_t hrs = p["hours"] | p["hour"] | 0;
                uint32_t total_sec = secs + (mins * 60) + (hrs * 3600);
                String label = p["label"].is<String>() ? p["label"].as<String>() : "TIMER";
                if (total_sec > 0) {
                    StartTimer(total_sec, label);
                }
            }
            else if (event == "jarvis.alarm" || msg_type == "jarvis.alarm") {
                JsonObject p = doc["payload"].is<JsonObject>() ? doc["payload"] : doc.as<JsonObject>();
                int hr = p["hour"] | p["hr"] | -1;
                int min = p["minute"] | p["min"] | -1;
                String label = p["label"].is<String>() ? p["label"].as<String>() : "ALARME";
                if (hr >= 0 && min >= 0) {
                    SetAlarm(hr, min, label);
                    SetDisplayMode(DisplayMode::kAlarm);
                }
            }
            else if (event == "jarvis.ze_status" || event == "ze_delivery") {
                JsonObject p = doc["payload"].is<JsonObject>() ? doc["payload"] : doc.as<JsonObject>();
                if (p["number"].is<const char*>() || p["number"].is<String>()) g_ze_order_number = p["number"].as<String>();
                if (p["status"].is<const char*>() || p["status"].is<String>()) g_ze_status = p["status"].as<String>();
                if (p["items"].is<const char*>() || p["items"].is<String>()) g_ze_items = p["items"].as<String>();
                if (p["total"].is<float>() || p["total"].is<int>()) g_ze_total = p["total"].as<float>();
                if (p["updated_at"].is<const char*>() || p["updated_at"].is<String>()) g_ze_updated_at = p["updated_at"].as<String>();
                bool show = p["show"] | true;
                if (show) SetDisplayMode(DisplayMode::kZeDelivery);
            }

        }

    } else if (type == WStype_DISCONNECTED) {
        s_ws_drops++;
        LogWs(audio_channel ? "VOZ" : "CTRL", "DISCONNECTED", "len=" + String((unsigned)length));
        if (audio_channel) {
            g_audio_authenticated = false;
            ResetMicSpeechGate();
        }
        if (g_current_mode == DisplayMode::kVoiceListening ||
            g_current_mode == DisplayMode::kVoiceTranscribing ||
            g_current_mode == DisplayMode::kVoiceSending ||
            g_current_mode == DisplayMode::kVoiceThinking) {
            SetDisplayMode(DisplayMode::kStandby);
        }
    } else if (type == WStype_ERROR) {
        LogWs(audio_channel ? "VOZ" : "CTRL", "ERROR", "len=" + String((unsigned)length));
        } else if (type == WStype_BIN) {
        g_last_tts_time = millis();
        g_last_tts_play_ms = millis();
        if (g_tts_ringbuffer && length > 0) {
            portENTER_CRITICAL(&g_tts_mux);
            for (size_t i = 0; i < length; ++i) {
                if (g_tts_rb_count < kTtsRingBufferSize) {
                    g_tts_ringbuffer[g_tts_rb_head] = payload[i];
                    g_tts_rb_head = (g_tts_rb_head + 1) % kTtsRingBufferSize;
                    g_tts_rb_count++;
                }
            }
            portEXIT_CRITICAL(&g_tts_mux);
        }
    }
}

void WebSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    ProcessWebSocketEvent(g_web_socket, false, type, payload, length);
}

void AudioWebSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    ProcessWebSocketEvent(g_audio_web_socket, true, type, payload, length);
}

// Pre-roll local no ESP32: armazena os ultimos 12 quadros Opus (~720ms) antes do inicio da fala
constexpr size_t kOpusPreRollCount = 12;
struct OpusPreRollPacket {
    uint8_t data[256];
    size_t len = 0;
};
static OpusPreRollPacket s_preroll_packets[kOpusPreRollCount];
static size_t s_preroll_idx = 0;
static bool s_preroll_full = false;

void AudioTask(void* pvParameters) {
    while (true) {
        if (WiFi.status() == WL_CONNECTED && g_web_socket.isConnected()) {
            // Trava de Mute / Anti-Eco por Hardware:
            // Enquanto o alto-falante estiver tocando ou tocou ha menos de 1000ms, o microfone e 100% ignorado!
            if (g_tts_rb_count > 0 || (millis() - g_last_tts_play_ms < 1000)) {
                g_mic_speech_active = false;
                g_mic_silence_frames = 0;
                s_preroll_idx = 0;
                s_preroll_full = false;
                g_wake_word_engine.Reset();
                vTaskDelay(pdMS_TO_TICKS(15));
                continue;
            }

            static uint8_t mono_buf[512];
            size_t bytes_read = 0;
            for (int _i = 0; _i < 16; _i++) {
                esp_err_t err = i2s_read(kI2sPortNum, mono_buf, sizeof(mono_buf), &bytes_read, 0);
                if (err != ESP_OK || bytes_read == 0) break;

                // Barramento mono I2S_CHANNEL_FMT_ONLY_LEFT: 2 bytes por amostra int16_t
                size_t num_samples = bytes_read / 2;
                const int16_t* samples = reinterpret_cast<const int16_t*>(mono_buf);

                if (!g_mic_speech_active) {
                    int16_t boosted_samples[256];
                    size_t n_boost = num_samples < 256 ? num_samples : 256;
                    for (size_t s = 0; s < n_boost; ++s) {
                        int32_t b = static_cast<int32_t>(samples[s]) * 3;
                        if (b > 32767) b = 32767;
                        if (b < -32768) b = -32768;
                        boosted_samples[s] = static_cast<int16_t>(b);
                    }
                    if (g_wake_word_engine.ProcessSamples(boosted_samples, n_boost)) {
                        g_mic_speech_active = true;
                        g_mic_silence_frames = 0;
                        Serial.println("[WAKEWORD-LOCAL] *** WAKE WORD 'HEY JARVIS' DETECTADA LOCALMENTE NA ESFERA! ***");
                        SetDisplayMode(DisplayMode::kVoiceListening);
                        PlayWakeBeep();
                        g_web_socket.sendTXT("{\"type\":\"voice_start\"}");

                        // Despeja imediatamente os pacotes Opus acumulados no pre-roll circular
                        size_t count = s_preroll_full ? kOpusPreRollCount : s_preroll_idx;
                        size_t start = s_preroll_full ? s_preroll_idx : 0;
                        for (size_t p = 0; p < count; ++p) {
                            size_t idx = (start + p) % kOpusPreRollCount;
                            if (s_preroll_packets[idx].len > 0) {
                                g_web_socket.sendBIN(s_preroll_packets[idx].data, s_preroll_packets[idx].len);
                            }
                        }
                        s_preroll_idx = 0;
                        s_preroll_full = false;
                    }
                }

                for (size_t s = 0; s < num_samples; ++s) {
                    if (g_opus_pcm_accum_count < static_cast<size_t>(kOpusFrameSamples)) {
                        g_opus_pcm_accum[g_opus_pcm_accum_count++] = samples[s];
                    }
                }

                if (g_opus_pcm_accum_count >= static_cast<size_t>(kOpusFrameSamples)) {
                    g_opus_pcm_accum_count = 0;

                    double energy = 0.0;
                    for (int s = 0; s < kOpusFrameSamples; ++s) {
                        double val = g_opus_pcm_accum[s];
                        energy += val * val;
                    }
                    float rms = static_cast<float>(sqrt(energy / kOpusFrameSamples));
                    float threshold = max(420.0f, g_mic_noise_floor * 2.2f);

                    static unsigned long s_last_mic_dbg = 0;
                    if (millis() - s_last_mic_dbg > 4000) {
                        s_last_mic_dbg = millis();
                        Serial.printf("[OPUS-MIC] RMS=%.1f Floor=%.1f Active=%d Thresh=%.1f\n",
                                      rms, g_mic_noise_floor, g_mic_speech_active, threshold);
                    }

                    g_opus_packet_buf[0] = 'O';
                    g_opus_packet_buf[1] = 'P';
                    g_opus_packet_buf[2] = 'U';
                    g_opus_packet_buf[3] = 'S';
                    opus_int32 enc_bytes = 0;
                    if (g_opus_encoder) {
                        enc_bytes = opus_encode(g_opus_encoder, g_opus_pcm_accum, kOpusFrameSamples,
                                                g_opus_packet_buf + 4, sizeof(g_opus_packet_buf) - 4);
                    }

                    if (enc_bytes > 0) {
                        size_t total_opus_bytes = enc_bytes + 4;

                        // Se a fala ainda NAO foi iniciada por Wake Word:
                        if (!g_mic_speech_active) {
                            // Repouso / Silencio / Conversa sem Wake Word:
                            // ZERO BYTES ENVIADOS PELA REDE!
                            // Apenas armazena no buffer circular de pre-roll local!
                            memcpy(s_preroll_packets[s_preroll_idx].data, g_opus_packet_buf, total_opus_bytes);
                            s_preroll_packets[s_preroll_idx].len = total_opus_bytes;
                            s_preroll_idx = (s_preroll_idx + 1) % kOpusPreRollCount;
                            if (s_preroll_idx == 0) s_preroll_full = true;
                        } else {
                            // Fala ativa apos Wake Word: transmite o comando continuamente
                            g_web_socket.sendBIN(g_opus_packet_buf, total_opus_bytes);

                            if (rms < 350.0f) {
                                if (++g_mic_silence_frames >= 8) { // ~480ms de silencio
                                    g_mic_speech_active = false;
                                    g_mic_silence_frames = 0;
                                    Serial.println("[OPUS-MIC] Comando concluido -> enviando voice_end e ativando Thinking.");
                                    SetDisplayMode(DisplayMode::kVoiceThinking);
                                    g_web_socket.sendTXT("{\"type\":\"voice_end\"}");
                                }
                            } else {
                                g_mic_silence_frames = 0;
                            }
                        }
                    }
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}


void setup() {
    Serial.begin(115200);
    delay(500);

    pinMode(kBuiltinLedGpio, OUTPUT);
    digitalWrite(kBuiltinLedGpio, HIGH);

    pinMode(kBatteryAdcPin, INPUT);
    pinMode(kBatteryChargingPin, INPUT_PULLUP);

    g_lcd.init();
    SetDisplayMode(DisplayMode::kStandby);
    
    g_canvas.createSprite(240, 240);

    if (psramFound()) {
        g_tts_ringbuffer = (uint8_t*)heap_caps_malloc(kTtsRingBufferSize, MALLOC_CAP_SPIRAM);
        if (g_tts_ringbuffer) {
            Serial.printf("[PSRAM] Ringbuffer TTS de %u KB alocado com sucesso!\n", (unsigned)(kTtsRingBufferSize / 1024));
        }
    }
    if (!g_tts_ringbuffer) {
        g_tts_ringbuffer = (uint8_t*)malloc(32 * 1024);
        Serial.printf("[HEAP] Fallback Ringbuffer TTS alocado em SRAM interna (32 KB)\n");
    }

    InitializeES8311Codec();
    InitializeI2SAudio();
    InitializeOpusEncoder();
    g_wake_word_engine.Initialize();

    Serial.println("\n[+] Firmware J.A.R.V.I.S. v10.0 (microWakeWord TFLite ESP32-S3) OK!\n");

    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.setSleep(false); // DOC ESP32: modem-sleep causa picos de latência e quedas em streaming de áudio — voz precisa de rádio sempre ativo.
    WiFi.setTxPower(WIFI_POWER_19_5dBm);
    WiFi.begin(kDefaultSsid, kDefaultPass);

    configTime(-3 * 3600, 0, "a.st1.ntp.br", "pool.ntp.br", "time.nist.gov");

    SetupArduinoOta();

    g_web_socket.onEvent(WebSocketEvent);
    g_audio_web_socket.onEvent(AudioWebSocketEvent);

    // Feedback sonoro imediato de boot para validar alto-falante
    PlayWakeBeep();

    // Tarefa dedicada de áudio/Opus com 32 KB de Stack no Core 0 (evita stack overflow do loopTask)
    xTaskCreatePinnedToCore(AudioTask, "AudioTask", 32768, NULL, 5, NULL, 0);
}

void HandleSerialDiagnosticCommands() {
    while (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        if (cmd.length() == 0) continue;

        Serial.printf("\n>>> [CMD RECEBIDO] '%s'\n", cmd.c_str());

        if (cmd == "help" || cmd == "?") {
            Serial.println("==================================================");
            Serial.println("   J.A.R.V.I.S. COM3 - COMANDOS DE DIAGNOSTICO    ");
            Serial.println("==================================================");
            Serial.println(" diag / status  : Relatorio completo de hardware/memoria");
            Serial.println(" trigger        : Simula gatilho da Wake Word por software");
            Serial.println(" beep           : Toca o beep de ativacao no speaker");
            Serial.println(" reboot         : Reinicia o ESP32-S3");
            Serial.println(" thresh <num>   : Ajusta limiar de prob Wake Word (ex: thresh 120)");
            Serial.println(" mode <0-8>     : Altera modo de exibicao da tela");
            Serial.println("==================================================");
        } else if (cmd == "diag" || cmd == "status") {
            Serial.println("\n--- [RELATORIO COMPLETO DE DIAGNOSTICO] ---");
            Serial.printf("Dispositivo      : J.A.R.V.I.S. Esfera ESP32-S3\n");
            Serial.printf("Firmware         : v10.0 (Local microWakeWord TFLite)\n");
            Serial.printf("Uptime           : %lu s\n", millis() / 1000);
            Serial.printf("Heap Livre       : %u bytes (Min: %u)\n", esp_get_free_heap_size(), esp_get_minimum_free_heap_size());
            if (psramFound()) {
                Serial.printf("PSRAM Livre      : %u / %u bytes\n", ESP.getFreePsram(), ESP.getPsramSize());
            } else {
                Serial.printf("PSRAM            : Nao disponivel\n");
            }
            Serial.printf("Modo Display     : %d\n", static_cast<int>(g_current_mode));
            BatteryStatus bat = ReadBatteryStatus();
            Serial.printf("Bateria          : %.2fV (%d%%) Carregando: %d\n", bat.voltage, bat.percentage, bat.is_charging);
            Serial.printf("Wi-Fi Status     : %s (IP: %s, RSSI: %d dBm)\n",
                          WiFi.status() == WL_CONNECTED ? "CONECTADO" : "DESCONECTADO",
                          WiFi.localIP().toString().c_str(), WiFi.RSSI());
            Serial.printf("WebSocket Server : %s:%d%s (Conectado: %d)\n",
                          kZimaOsWsHost, kZimaOsWsPort, kZimaOsWsPath, g_web_socket.isConnected());
            Serial.printf("Microfone        : FalaAtiva=%d, Floor=%.1f\n", g_mic_speech_active, g_mic_noise_floor);
            Serial.printf("Wake Word Local  : Pronto=%d Prob=%d Avg=%d Max=%d FeatMax=%u Thresh=%d Ignore=%d\n",
                          g_wake_word_engine.IsReady(),
                          g_wake_word_engine.GetLastProbability(),
                          g_wake_word_engine.GetAverageProbability(),
                          g_wake_word_engine.GetPeriodMaxProbability(),
                          g_wake_word_engine.GetLastFeatureMax(),
                          g_wake_word_engine.GetThreshold(),
                          g_wake_word_engine.GetIgnoreWindows());
            Serial.printf("TTS Ringbuffer   : %u / %u bytes (MuteGuard=%d)\n",
                          (unsigned)g_tts_rb_count, (unsigned)kTtsRingBufferSize,
                          (g_tts_rb_count > 0 || (millis() - g_last_tts_play_ms < 1000)));
            Serial.println("-------------------------------------------\n");
        } else if (cmd == "trigger") {
            Serial.println("[CMD] Disparando gatilho Wake Word por comando serial!");
            g_mic_speech_active = true;
            g_mic_silence_frames = 0;
            SetDisplayMode(DisplayMode::kVoiceListening);
            PlayWakeBeep();
            g_web_socket.sendTXT("{\"type\":\"voice_start\"}");
        } else if (cmd == "beep") {
            Serial.println("[CMD] Tocando beep de ativacao...");
            PlayWakeBeep();
        } else if (cmd == "reboot") {
            Serial.println("[CMD] Reiniciando ESP32...");
            delay(100);
            ESP.restart();
        } else if (cmd.startsWith("thresh ")) {
            int th = cmd.substring(7).toInt();
            if (th > 0 && th <= 255) {
                g_wake_word_engine.SetThreshold(static_cast<uint8_t>(th));
                Serial.printf("[CMD] Limiar de Wake Word atualizado para %d / 255 (~%.2f)\n", th, th / 255.0f);
            }
        } else if (cmd.startsWith("mode ")) {
            int m = cmd.substring(5).toInt();
            SetDisplayMode(static_cast<DisplayMode>(m));
            Serial.printf("[CMD] Modo de display alterado para %d\n", m);
        } else {
            Serial.printf("[CMD] Comando '%s' desconhecido. Digite 'help' para ajuda.\n", cmd.c_str());
        }
    }
}

void PrintPeriodicDiagnosticHeartbeat() {
    static unsigned long s_last_hb = 0;
    if (millis() - s_last_hb < 3000) return;
    s_last_hb = millis();

    const char* mode_name = "DESCONHECIDO";
    switch (g_current_mode) {
        case DisplayMode::kStandby: mode_name = "STANDBY"; break;
        case DisplayMode::kHappy: mode_name = "HAPPY"; break;
        case DisplayMode::kSpotify: mode_name = "SPOTIFY"; break;
        case DisplayMode::kTelemetry: mode_name = "TELEMETRY"; break;
        case DisplayMode::kZeDelivery: mode_name = "ZE_DELIVERY"; break;
        case DisplayMode::kVoiceListening: mode_name = "VOICE_LISTENING"; break;
        case DisplayMode::kVoiceThinking: mode_name = "VOICE_THINKING"; break;
        case DisplayMode::kVoiceSuccess: mode_name = "VOICE_SUCCESS"; break;
        case DisplayMode::kVoiceError: mode_name = "VOICE_ERROR"; break;
        case DisplayMode::kCard: mode_name = "CARD"; break;
        default: break;
    }

    Serial.printf("[DIAG] Modo=%s | WiFi=%d dBm | Heap=%uK PSRAM=%uK | MicFala=%d | WakeProb=%d/255 Avg=%d Feat=%u Thresh=%d | TTS=%uK\n",
                  mode_name,
                  WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0,
                  esp_get_free_heap_size() / 1024,
                  psramFound() ? (ESP.getFreePsram() / 1024) : 0,
                  g_mic_speech_active,
                  g_wake_word_engine.GetLastProbability(),
                  g_wake_word_engine.GetAverageProbability(),
                  g_wake_word_engine.GetLastFeatureMax(),
                  g_wake_word_engine.GetThreshold(),
                  (unsigned)(g_tts_rb_count / 1024));
}

void loop() {
    HandleSerialDiagnosticCommands();
    PrintPeriodicDiagnosticHeartbeat();
    ArduinoOTA.handle();
    HandleDirectTelemetryUdp();

    if (WiFi.status() == WL_CONNECTED) {
        if (!g_control_ws_started) {
            g_web_socket.begin(kZimaOsWsHost, kZimaOsWsPort, kZimaOsWsPath);
            // DOC WebSocketsClient: heartbeat mantém a conexão viva através de
            // NAT/firewall (ping a cada 15s, espera pong 3s, 2 falhas = desconecta)
            // e reconnect controlado evita o spam de "sessão assumida".
            g_web_socket.enableHeartbeat(15000, 3000, 2);
            g_web_socket.setReconnectInterval(3000);
            g_control_ws_started = true;
            FetchCatanduvaWeather();
            g_last_weather_fetch = millis();
            Serial.println("[WS] Controle da tela iniciado na porta 8095.");
        }

        if (!g_audio_ws_started) {
            g_audio_ws_started = true;
        }
        g_web_socket.loop();

                // Drena o ringbuffer de TTS da PSRAM no speaker (zero memmove, playback 100% fluido).
        if (g_tts_rb_count > 0 && g_tts_ringbuffer) {
            uint8_t play_chunk[1024];
            size_t to_read = 0;
            portENTER_CRITICAL(&g_tts_mux);
            to_read = g_tts_rb_count < sizeof(play_chunk) ? g_tts_rb_count : sizeof(play_chunk);
            for (size_t i = 0; i < to_read; ++i) {
                play_chunk[i] = g_tts_ringbuffer[g_tts_rb_tail];
                g_tts_rb_tail = (g_tts_rb_tail + 1) % kTtsRingBufferSize;
            }
            g_tts_rb_count -= to_read;
            portEXIT_CRITICAL(&g_tts_mux);

            size_t written = 0;
            if (i2s_write(kI2sPortNum, play_chunk, to_read, &written, pdMS_TO_TICKS(15)) == ESP_OK && written > 0) {
                g_last_tts_time = millis();
                g_last_tts_play_ms = millis();
            }
        }

if (millis() - g_last_weather_fetch > 600000) {
            g_last_weather_fetch = millis();
            FetchCatanduvaWeather();
        }
    } else {
        if (millis() - g_last_wifi_check > 5000) {
            g_last_wifi_check = millis();
            WiFi.begin(kDefaultSsid, kDefaultPass);
        }
    }

    if (g_voice_status_until > 0 && static_cast<long>(millis() - g_voice_status_until) >= 0 &&
        (g_current_mode == DisplayMode::kVoiceSuccess || g_current_mode == DisplayMode::kVoiceError)) {
        SetDisplayMode(DisplayMode::kStandby);
    }

    // Retorno automático para a página inicial (Standby / Relógio NTP) após 6s de inatividade após voz/cards
    if ((g_current_mode == DisplayMode::kHappy || g_current_mode == DisplayMode::kCard) &&
        g_last_tts_time > 0 && (millis() - g_last_tts_time > 6000)) {
        SetDisplayMode(DisplayMode::kStandby);
    }

    // Verificação de Expiração do Timer Regressivo
    if (g_timer_active && !g_timer_paused) {
        if (millis() >= g_timer_end_ms) {
            g_timer_active = false;
            g_alarm_ringing = true;
            g_alarm_label = g_timer_label + " TEMPO!";
            SetDisplayMode(DisplayMode::kAlarm);
            Serial.println("[TIMER] Timer finalizado! Alarme ativado.");
        }
    }

    // Verificação do Alarme Programado NTP
    if (g_alarm_active && !g_alarm_ringing) {
        struct tm timeinfo;
        if (getLocalTime(&timeinfo)) {
            if (timeinfo.tm_hour == g_alarm_hour && timeinfo.tm_min == g_alarm_minute && timeinfo.tm_sec < 5) {
                g_alarm_ringing = true;
                SetDisplayMode(DisplayMode::kAlarm);
                Serial.printf("[ALARME] Hora do alarme atingida (%02d:%02d)!\n", g_alarm_hour, g_alarm_minute);
            }
        }
    }

    // Tocar Som de Alarme Se Estiver Tocando
    if (g_alarm_ringing) {
        PlayAlarmBeepTone();
    }

    // Leitura e Processamento do Toque na Tela (Swipe vs Tap)
    uint16_t raw_touch_x = 0, raw_touch_y = 0;
    bool currently_touching = g_lcd.getTouch(&raw_touch_x, &raw_touch_y);

    if (currently_touching) {
        int tx = static_cast<int>(raw_touch_x);
        int ty = static_cast<int>(raw_touch_y);

        if (!g_is_touching) {
            g_is_touching = true;
            g_touch_start_x = tx;
            g_touch_start_y = ty;
            g_touch_start_time = millis();
        }
        g_touch_current_x = tx;
        g_touch_current_y = ty;
        g_touch_release_time = 0;
    } else if (g_is_touching) {
        if (g_touch_release_time == 0) {
            g_touch_release_time = millis();
        } else if (millis() - g_touch_release_time > 50) {
            g_is_touching = false;
            g_touch_release_time = 0;

            int dx = g_touch_current_x - g_touch_start_x;
            int dy = g_touch_current_y - g_touch_start_y;
            float dist = sqrtf(static_cast<float>(dx * dx + dy * dy));

            if (dist > 40.0f) {
                // Gesto de Arrastar (SWIPE)
                String direction;
                if (abs(dx) > abs(dy)) {
                    direction = (dx > 0) ? "RIGHT" : "LEFT";
                } else {
                    direction = (dy > 0) ? "DOWN" : "UP";
                }

                if (g_web_socket.isConnected()) {
                    JsonDocument doc;
                    doc["type"] = "custom";
                    doc["payload"]["event"] = "jarvis.swipe";
                    doc["payload"]["direction"] = direction;
                    String json_str;
                    serializeJson(doc, json_str);
                    g_web_socket.sendTXT(json_str);
                }

                Serial.println("[TOUCH] Gesto Arrastar (Swipe): " + direction);
                // DO NOT trigger button tap or close screen on swipe!
            } else {
                // Toque Simples (TAP / CLIQUE)
                if (g_current_mode == DisplayMode::kCard) {
                    String clicked_btn = "";
                    if (g_current_button3_id.length() > 0) {
                        if (g_touch_current_x < 85) clicked_btn = g_current_button1_id;
                        else if (g_touch_current_x <= 155) clicked_btn = g_current_button2_id;
                        else clicked_btn = g_current_button3_id;
                    } else {
                        clicked_btn = (g_touch_current_x < 120) ? g_current_button1_id : g_current_button2_id;
                    }

                    if (clicked_btn.length() > 0 && g_web_socket.isConnected()) {

                        JsonDocument resp;
                        resp["type"] = "custom";
                        resp["payload"]["event"] = "jarvis.button_clicked";
                        resp["payload"]["request_id"] = g_current_request_id;
                        resp["payload"]["button_id"] = clicked_btn;
                        String json_str;
                        serializeJson(resp, json_str);
                        g_web_socket.sendTXT(json_str);
                    }
                    // Toque derruba o card explicitamente (limpa o hold antes do Standby)
                    g_is_custom_screen_active = false;
                    g_custom_screen_hold_until = 0;
                    SetDisplayMode(DisplayMode::kStandby);
                } else if (g_current_mode == DisplayMode::kSpotify) {
                    if (!HandleSpotifyTap(g_touch_current_x, g_touch_current_y)) {
                        SetDisplayMode(DisplayMode::kTelemetry);
                    }

                } else if (g_current_mode == DisplayMode::kTelemetry) {
                    SetDisplayMode(DisplayMode::kZeDelivery);
                } else if (g_current_mode == DisplayMode::kZeDelivery) {
                    int tx = g_touch_current_x;
                    int ty = g_touch_current_y;
                    if (tx >= 45 && tx <= 118 && ty >= 144 && ty <= 182) {
                        // Botão REFRESH
                        if (g_web_socket.isConnected()) {
                            JsonDocument req;
                            req["type"] = "custom";
                            req["payload"]["event"] = "ze_refresh";
                            String json_str;
                            serializeJson(req, json_str);
                            g_web_socket.sendTXT(json_str);
                        }
                    } else if (tx >= 122 && tx <= 195 && ty >= 144 && ty <= 182) {
                        // Botão VOLTAR
                        SetDisplayMode(DisplayMode::kStandby);
                    } else {
                        SetDisplayMode(DisplayMode::kStandby);
                    }
                } else if (g_current_mode == DisplayMode::kTimer) {
                    int tx = g_touch_current_x;
                    int ty = g_touch_current_y;
                    if (tx >= 30 && tx <= 110 && ty >= 165 && ty <= 215) {
                        if (g_timer_paused) {
                            g_timer_paused = false;
                            g_timer_end_ms = millis() + g_timer_pause_remaining_ms;
                            Serial.println("[TIMER] Retomado");
                        } else {
                            g_timer_paused = true;
                            g_timer_pause_remaining_ms = (g_timer_end_ms > millis()) ? (g_timer_end_ms - millis()) : 0;
                            Serial.println("[TIMER] Pausado");
                        }
                    } else if (tx >= 125 && tx <= 205 && ty >= 165 && ty <= 215) {
                        g_timer_active = false;
                        g_timer_paused = false;
                        SetDisplayMode(DisplayMode::kStandby);
                        Serial.println("[TIMER] Cancelado");
                    }
                } else if (g_current_mode == DisplayMode::kAlarm) {
                    int tx = g_touch_current_x;
                    int ty = g_touch_current_y;
                    if (tx >= 30 && tx <= 210 && ty >= 160 && ty <= 220) {
                        g_alarm_ringing = false;
                        g_alarm_active = false;
                        SetDisplayMode(DisplayMode::kStandby);
                        Serial.println("[ALARME] Desligado pelo toque");
                    }
                } else {
                    if (g_current_mode == DisplayMode::kStandby) SetDisplayMode(DisplayMode::kHappy);
                    else if (g_current_mode == DisplayMode::kHappy) SetDisplayMode(DisplayMode::kSpotify);
                    else if (g_current_mode == DisplayMode::kSpotify) SetDisplayMode(DisplayMode::kTelemetry);
                    else if (g_current_mode == DisplayMode::kTelemetry) SetDisplayMode(DisplayMode::kZeDelivery);
                    else if (g_current_mode == DisplayMode::kZeDelivery) SetDisplayMode(DisplayMode::kSad);
                    else if (g_current_mode == DisplayMode::kSad) SetDisplayMode(DisplayMode::kAngry);
                    else SetDisplayMode(DisplayMode::kStandby);
                }
            }
        }
    }

    // Renderização da Tela com taxa de atualização estável (~15 FPS / 66ms) para eliminar Flicker no LCD GC9A01
    static unsigned long s_last_render_time = 0;
    if (millis() - s_last_render_time > 66) {
        s_last_render_time = millis();
        if (g_current_mode == DisplayMode::kStandby) {
            DrawStandbyClockWeather();
        } else if (g_current_mode == DisplayMode::kSpotify) {
            DrawSpotifyScreen();
        } else if (g_current_mode == DisplayMode::kTelemetry) {
            DrawTelemetryScreen();
        } else if (g_current_mode == DisplayMode::kZeDelivery) {
            DrawZeDeliveryScreen();
        } else if (g_current_mode == DisplayMode::kHappy || g_current_mode == DisplayMode::kSad || g_current_mode == DisplayMode::kAngry) {
            DrawRobotFace(g_current_mode);
        } else if (g_current_mode == DisplayMode::kVoiceListening) {
            DrawRobotFace(g_current_mode);
        } else if (g_current_mode == DisplayMode::kVoiceTranscribing || g_current_mode == DisplayMode::kVoiceSending ||
                   g_current_mode == DisplayMode::kVoiceThinking || g_current_mode == DisplayMode::kVoiceQueued ||
                   g_current_mode == DisplayMode::kVoiceSuccess || g_current_mode == DisplayMode::kVoiceError) {
            DrawVoiceProgressScreen(g_current_mode);
        } else if (g_current_mode == DisplayMode::kTimer) {
            DrawTimerScreen();
        } else if (g_current_mode == DisplayMode::kAlarm) {
            DrawAlarmScreen();
        }
    }

    delay(10);

}
