#include "services/Esp32WifiService.h"

#include <WiFi.h>
#include <Preferences.h>

namespace {
int scanCount = -1;
bool gathering = false;
bool scanRunning = false;
uint32_t nextScanAt = 0;
uint32_t scanSequence = 0;
int emitIndex = 0;
Preferences wifiPreferences;
String savedSsid;
String savedPassword;

int hexNibble(char value) {
  if (value >= 48 && value <= 57) return value - 48;
  if (value >= 65 && value <= 70) return value - 55;
  if (value >= 97 && value <= 102) return value - 87;
  return -1;
}

bool decodeHexText(const String &hex, String &output) {
  if (!hex.length() || (hex.length() & 1)) return false;
  output = "";
  output.reserve(hex.length() / 2);
  for (size_t index = 0; index < hex.length(); index += 2) {
    const int high = hexNibble(hex[index]);
    const int low = hexNibble(hex[index + 1]);
    if (high < 0 || low < 0) return false;
    output += char((high << 4) | low);
  }
  return true;
}

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
bool begin(const char *defaultSsid, const char *defaultPassword) {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(false, false);
  wifiPreferences.begin("noob-wifi", false);
  savedSsid = wifiPreferences.getString("ssid", "");
  savedPassword = wifiPreferences.getString("password", "");
  if (savedSsid.isEmpty() && defaultSsid && defaultSsid[0]) {
    savedSsid = defaultSsid;
    savedPassword = defaultPassword ? defaultPassword : "";
    wifiPreferences.putString("ssid", savedSsid);
    wifiPreferences.putString("password", savedPassword);
  }
  return true;
}

NativeResult connect(const int32_t *arguments, uint8_t count) {
  if (savedSsid.isEmpty()) return {false, 0, "Wi-Fi credentials not set"};
  const uint32_t timeout = count ? constrain(arguments[0], 1000, 30000) : 15000;
  gathering = false;
  if (scanRunning) WiFi.scanDelete();
  scanRunning = false;
  WiFi.begin(savedSsid.c_str(), savedPassword.c_str());
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < timeout) delay(50);
  if (WiFi.status() != WL_CONNECTED)
    return {false, int32_t(WiFi.status()), "connect timeout ssid_hex=" + hexText(savedSsid)};
  return {true, WiFi.RSSI(), "ssid_hex=" + hexText(savedSsid) +
                            " ip=" + WiFi.localIP().toString()};
}

NativeResult disconnect(const int32_t *, uint8_t) {
  WiFi.disconnect(false, false);
  return {true, 0, "disconnected credentials_preserved=1"};
}

NativeResult status(const int32_t *, uint8_t) {
  const bool linked = WiFi.status() == WL_CONNECTED;
  return {true, linked ? WiFi.RSSI() : 0,
          "connected=" + String(linked ? 1 : 0) +
              " configured=" + String(savedSsid.isEmpty() ? 0 : 1) +
              (linked ? " ip=" + WiFi.localIP().toString() : "")};
}

NativeResult setCredentials(const String &arguments) {
  const int separator = arguments.indexOf(32);
  if (separator < 1) return {false, 0, "usage: SSID_HEX PASSWORD_HEX"};
  String ssid;
  String password;
  if (!decodeHexText(arguments.substring(0, separator), ssid) ||
      !decodeHexText(arguments.substring(separator + 1), password) ||
      ssid.length() > 32 || password.length() > 63) {
    return {false, 0, "invalid hex or credential length"};
  }
  savedSsid = ssid;
  savedPassword = password;
  wifiPreferences.putString("ssid", savedSsid);
  wifiPreferences.putString("password", savedPassword);
  return {true, 1, "updated ssid_hex=" + hexText(savedSsid)};
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
