#include "services/Esp32WifiService.h"

#include <WiFi.h>

namespace {
int scanCount = -1;
bool gathering = false;
bool scanRunning = false;
uint32_t nextScanAt = 0;
uint32_t scanSequence = 0;
int emitIndex = 0;

String hexText(const String &text) {
  static const char digits[] = "0123456789ABCDEF";
  String result;
  result.reserve(text.length() * 2);
  for (size_t i = 0; i < text.length(); ++i) {
    const uint8_t value = static_cast<uint8_t>(text[i]);
    result += digits[value >> 4];
    result += digits[value & 0x0f];
  }
  return result;
}

class RssiGatherer : public NoobBackgroundService {
 public:
  bool tick(String &event) override {
    if (!gathering) return false;
    if (scanRunning) {
      const int result = WiFi.scanComplete();
      if (result == WIFI_SCAN_RUNNING) return false;
      scanRunning = false;
      scanCount = result < 0 ? 0 : result;
      emitIndex = 0;
      ++scanSequence;
      if (!scanCount) {
        event = "NRP/1 0 EVENT RSSI scan=" + String(scanSequence) +
                " networks=0";
        nextScanAt = millis() + 1000;
        return true;
      }
    }
    if (emitIndex < scanCount) {
      const int index = emitIndex++;
      event = "NRP/1 0 EVENT RSSI scan=" + String(scanSequence) +
              " index=" + String(index) +
              " rssi=" + String(WiFi.RSSI(index)) +
              " ssid_hex=" + hexText(WiFi.SSID(index)) +
              " channel=" + String(WiFi.channel(index));
      if (emitIndex == scanCount) nextScanAt = millis() + 1000;
      return true;
    }
    if (static_cast<int32_t>(millis() - nextScanAt) >= 0) {
      WiFi.scanDelete();
      WiFi.scanNetworks(true, true);
      scanRunning = true;
    }
    return false;
  }
};

RssiGatherer gatherer;
}

namespace Esp32WifiService {
bool begin() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(false, false);
  return true;
}

NativeResult scan(const int32_t *, uint8_t) {
  if (gathering) return {false, 0, "RSSI gathering is active"};
  WiFi.scanDelete();
  scanCount = WiFi.scanNetworks(false, true);
  if (scanCount < 0) return {false, scanCount, "scan failed"};
  return {true, scanCount, "networks=" + String(scanCount)};
}

NativeResult rssi(const int32_t *arguments, uint8_t count) {
  if (scanCount < 0) return {false, 0, "run WIFI_SCAN first"};
  const int32_t index = count ? arguments[0] : 0;
  if (index < 0 || index >= scanCount)
    return {false, 0, "network index out of range"};
  return {true, WiFi.RSSI(index),
          "index=" + String(index) + " ssid_hex=" + hexText(WiFi.SSID(index)) +
              " channel=" + String(WiFi.channel(index)) +
              " encryption=" +
              String(static_cast<int>(WiFi.encryptionType(index)))};
}

NativeResult rssiOn(const int32_t *, uint8_t) {
  if (gathering) return {true, 1, "already_on interval_ms=1000"};
  WiFi.scanDelete();
  scanCount = -1;
  emitIndex = 0;
  nextScanAt = millis();
  scanRunning = false;
  gathering = true;
  return {true, 1, "on interval_ms=1000"};
}

NativeResult rssiOff(const int32_t *, uint8_t) {
  gathering = false;
  if (scanRunning) WiFi.scanDelete();
  scanRunning = false;
  scanCount = -1;
  emitIndex = 0;
  return {true, 0, "off"};
}

NoobBackgroundService &rssiService() { return gatherer; }
}
