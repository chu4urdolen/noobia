#if defined(ESP32) && defined(NOOB_USE_NIMBLE)
#include "transport/noob_ble_client_transport.h"

#include <Preferences.h>
#include <esp_log.h>

// Arduino's weak default releases BLE controller memory during initArduino().
// This backend owns that memory even though Arduino's BLE library is disabled.
extern "C" bool bleInUse(void) { return true; }

namespace {
BleClientTransport *activeTransport = nullptr;
Preferences blePreferences;
constexpr const char *TAG = "noob_nimble";

class ClientCallbacks : public NimBLEClientCallbacks {
 public:
  void onDisconnect(NimBLEClient *, int) override {
    if (activeTransport) activeTransport->handleDisconnect();
  }
};
ClientCallbacks clientCallbacks;

class ScanCallbacks : public NimBLEScanCallbacks {
 public:
  void onResult(const NimBLEAdvertisedDevice *device) override {
    if (activeTransport) activeTransport->handleAdvertisement(device);
  }
  void onScanEnd(const NimBLEScanResults &results, int reason) override {
    if (activeTransport) activeTransport->handleScanComplete(results, reason);
  }
};
ScanCallbacks scanCallbacks;

void notificationCallback(NimBLERemoteCharacteristic *, uint8_t *data,
                          size_t length, bool) {
  if (activeTransport) activeTransport->handleNotification(data, length);
}

bool macConfigured(const String &mac) {
  if (mac.length() != 17 || mac == "00:00:00:00:00:00") return false;
  for (int index = 0; index < 17; ++index) {
    if ((index + 1) % 3 == 0) {
      if (mac[index] != ':') return false;
    } else if (!isHexadecimalDigit(mac[index])) {
      return false;
    }
  }
  return true;
}
}  // namespace

BleClientTransport::BleClientTransport(const char *peerMac,
    const char *serviceUuid, const char *downlinkUuid, const char *uplinkUuid,
    uint32_t retryIntervalMs, uint8_t scanDurationSeconds)
    : peerMac_(peerMac ? peerMac : ""), serviceUuid_(serviceUuid),
      downlinkUuid_(downlinkUuid), uplinkUuid_(uplinkUuid),
      retryIntervalMs_(retryIntervalMs),
      scanDurationSeconds_(scanDurationSeconds) {
  peerMac_.toLowerCase();
}

bool BleClientTransport::begin(const char *localName) {
  blePreferences.begin("noob-ble", false);
  const String savedPeer = blePreferences.getString("peer", "");
  if (macConfigured(savedPeer)) peerMac_ = savedPeer;
  if (!macConfigured(peerMac_)) return false;
  if (!NimBLEDevice::init(localName ? localName : "Noob")) {
    ESP_LOGE(TAG, "NimBLE initialization failed");
    return false;
  }
  NimBLEDevice::setMTU(517);
  NimBLEScan *scanner = NimBLEDevice::getScan();
  scanner->setScanCallbacks(&scanCallbacks, false);
  scanner->setActiveScan(true);
  activeTransport = this;
  initialized_ = true;
  nextAttemptAt_ = millis();
  ESP_LOGI(TAG, "NimBLE ready, peer=%s", peerMac_.c_str());
  return true;
}

NativeResult BleClientTransport::scan(const int32_t *arguments, uint8_t count) {
  if (!activeTransport || !activeTransport->initialized_)
    return {false, 0, "BLE unavailable"};
  const uint8_t seconds = count
      ? static_cast<uint8_t>(constrain(arguments[0], 1, 10)) : 3;
  NimBLEScan *scanner = NimBLEDevice::getScan();
  if (activeTransport->scanRunning_) {
    scanner->stop();
    activeTransport->scanRunning_ = false;
  }
  NimBLEScanResults results = scanner->getResults(seconds * 1000, false);
  String detail = "devices=" + String(results.getCount());
  const int shown = min(results.getCount(), 8);
  for (int index = 0; index < shown; ++index) {
    const NimBLEAdvertisedDevice *device = results.getDevice(index);
    if (device) detail += " [" + String(index) + "]=" +
                         String(device->getAddress().toString().c_str()) +
                         "," + String(device->getRSSI());
  }
  const int total = results.getCount();
  scanner->clearResults();
  activeTransport->nextAttemptAt_ = millis() +
                                    activeTransport->retryIntervalMs_;
  return {true, total, detail};
}

NativeResult BleClientTransport::setPeer(const String &arguments) {
  if (!activeTransport) return {false, 0, "BLE unavailable"};
  String mac = arguments;
  mac.trim();
  mac.toLowerCase();
  if (!macConfigured(mac)) return {false, 0, "invalid BLE MAC"};
  if (activeTransport->client_ && activeTransport->client_->isConnected())
    activeTransport->client_->disconnect();
  activeTransport->peerMac_ = mac;
  blePreferences.putString("peer", mac);
  activeTransport->nextAttemptAt_ = millis();
  return {true, 1, "peer=" + mac + " reconnect_scheduled=1"};
}

NativeResult BleClientTransport::nativeStatus(const int32_t *, uint8_t) {
  if (!activeTransport) return {false, 0, "BLE unavailable"};
  return {true, activeTransport->connected() ? 1 : 0,
          activeTransport->status()};
}

const char *BleClientTransport::name() const { return "ble-client"; }

bool BleClientTransport::receive(String &message) {
  maintainConnection();
  if (pendingFrame_.isEmpty()) return false;
  message = pendingFrame_;
  pendingFrame_ = "";
  return true;
}

void BleClientTransport::send(const String &message) {
  maintainConnection();
  if (connected()) uplink_->writeValue(message.c_str(), message.length(), true);
}

bool BleClientTransport::connected() const {
  return client_ && client_->isConnected() && downlink_ && uplink_;
}

String BleClientTransport::status() const {
  if (!macConfigured(peerMac_)) return "disabled:no-peer-mac";
  return connected() ? "connected:" + peerMac_ : "disconnected:" + peerMac_;
}

void BleClientTransport::handleNotification(const uint8_t *data, size_t length) {
  pendingFrame_ = String(reinterpret_cast<const char *>(data), length);
  pendingFrame_.trim();
}

void BleClientTransport::handleDisconnect() {
  ESP_LOGW(TAG, "peer disconnected");
  downlink_ = nullptr;
  uplink_ = nullptr;
  nextAttemptAt_ = millis() + retryIntervalMs_;
}

void BleClientTransport::handleAdvertisement(const NimBLEAdvertisedDevice *device) {
  if (!device) return;
  String found(device->getAddress().toString().c_str());
  found.toLowerCase();
  if (found != peerMac_) return;
  pendingAddressType_ = device->getAddressType();
  pendingMatch_ = true;
}

void BleClientTransport::handleScanComplete(const NimBLEScanResults &, int) {
  scanRunning_ = false;
  NimBLEDevice::getScan()->clearResults();
  ESP_LOGI(TAG, "scan complete, peer_found=%d", pendingMatch_ ? 1 : 0);
  if (!pendingMatch_) nextAttemptAt_ = millis() + retryIntervalMs_;
}

void BleClientTransport::maintainConnection() {
  if (!initialized_ || connected() || scanRunning_) return;
  if (client_ && client_->isConnected()) {
    if (static_cast<int32_t>(millis() - nextAttemptAt_) < 0) return;
    client_->disconnect();
    downlink_ = nullptr;
    uplink_ = nullptr;
    nextAttemptAt_ = millis() + retryIntervalMs_;
    return;
  }
  if (pendingMatch_) {
    if (!connectMatch()) nextAttemptAt_ = millis() + retryIntervalMs_;
    return;
  }
  if (static_cast<int32_t>(millis() - nextAttemptAt_) < 0) return;
  if (!startScan()) nextAttemptAt_ = millis() + retryIntervalMs_;
}

bool BleClientTransport::startScan() {
  pendingMatch_ = false;
  scanRunning_ = NimBLEDevice::getScan()->start(
      scanDurationSeconds_ * 1000, false, true);
  return scanRunning_;
}

bool BleClientTransport::connectMatch() {
  if (!pendingMatch_) return false;
  pendingMatch_ = false;
  if (!client_) {
    client_ = NimBLEDevice::createClient();
    if (!client_) return false;
    client_->setClientCallbacks(&clientCallbacks, false);
    client_->setConnectTimeout(5000);
  }
  ESP_LOGI(TAG, "connecting to %s", peerMac_.c_str());
  if (!client_->connect(NimBLEAddress(peerMac_.c_str(), pendingAddressType_))) {
    ESP_LOGW(TAG, "GAP connect failed");
    return false;
  }
  NimBLERemoteService *service = client_->getService(serviceUuid_);
  if (!service) {
    ESP_LOGW(TAG, "Noob GATT service missing");
    client_->disconnect();
    return false;
  }
  downlink_ = service->getCharacteristic(downlinkUuid_);
  uplink_ = service->getCharacteristic(uplinkUuid_);
  if (!downlink_ || !uplink_ || !downlink_->canNotify() ||
      !uplink_->canWrite() || !downlink_->subscribe(true, notificationCallback)) {
    ESP_LOGW(TAG, "GATT characteristic or subscription failed");
    client_->disconnect();
    downlink_ = nullptr;
    uplink_ = nullptr;
    return false;
  }
  ESP_LOGI(TAG, "Noob GATT transport ready");
  return true;
}

#endif  // ESP32 && NOOB_USE_NIMBLE
