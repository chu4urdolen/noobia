#include "transport/BleClientTransport.h"
#include <BLEDevice.h>
#include <BLEScan.h>
#include <Preferences.h>

namespace {
BleClientTransport *activeTransport = nullptr;
Preferences blePreferences;
class ClientCallbacks : public BLEClientCallbacks {
  void onDisconnect(BLEClient *) override {
    if (activeTransport) activeTransport->handleDisconnect();
  }
};
void notificationCallback(BLERemoteCharacteristic *, uint8_t *data,
                          size_t length, bool) {
  if (activeTransport) activeTransport->handleNotification(data, length);
}
bool macConfigured(const String &mac) {
  if (mac.length() != 17 || mac == "00:00:00:00:00:00") return false;
  for (int index = 0; index < 17; ++index) {
    if ((index + 1) % 3 == 0) {
      if (mac[index] != 58) return false;
    } else if (!isHexadecimalDigit(mac[index])) {
      return false;
    }
  }
  return true;
}
}

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
  String savedPeer = blePreferences.getString("peer", "");
  if (macConfigured(savedPeer)) peerMac_ = savedPeer;
  if (!macConfigured(peerMac_)) return false;
  BLEDevice::init(localName ? localName : "Noob");
  activeTransport = this;
  initialized_ = true;
  nextAttemptAt_ = millis();
  return true;
}

NativeResult BleClientTransport::scan(const int32_t *arguments, uint8_t count) {
  if (!activeTransport || !activeTransport->initialized_)
    return {false, 0, "BLE unavailable"};
  const uint8_t seconds = count
      ? static_cast<uint8_t>(constrain(arguments[0], 1, 10)) : 3;
  BLEScan *scanner = BLEDevice::getScan();
  scanner->setActiveScan(true);
  BLEScanResults *results = scanner->start(seconds, false);
  if (!results) return {false, 0, "BLE scan failed"};
  String detail = "devices=" + String(results->getCount());
  const int shown = min(results->getCount(), 8);
  for (int index = 0; index < shown; ++index) {
    BLEAdvertisedDevice device = results->getDevice(index);
    detail += " [" + String(index) + "]=" +
              String(device.getAddress().toString().c_str()) + "," +
              String(device.getRSSI());
  }
  const int total = results->getCount();
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
  if (connected()) uplink_->writeValue(message, true);
}
bool BleClientTransport::connected() const {
  return client_ && client_->isConnected() && downlink_ && uplink_;
}
String BleClientTransport::status() const {
  if (!macConfigured(peerMac_)) return "disabled:no-peer-mac";
  return connected() ? "connected:" + peerMac_ : "disconnected:" + peerMac_;
}
void BleClientTransport::handleNotification(const uint8_t *data, size_t length) {
  // Each GATT notification is one protocol frame; framing above BLE is NRP/1.
  pendingFrame_ = String(reinterpret_cast<const char *>(data), length);
  pendingFrame_.trim();
}
void BleClientTransport::handleDisconnect() {
  downlink_ = nullptr;
  uplink_ = nullptr;
  nextAttemptAt_ = millis() + retryIntervalMs_;
}
void BleClientTransport::maintainConnection() {
  if (!initialized_ || connected()) return;
  if (static_cast<int32_t>(millis() - nextAttemptAt_) < 0) return;
  scanAndConnect();
  if (!connected()) nextAttemptAt_ = millis() + retryIntervalMs_;
}
bool BleClientTransport::scanAndConnect() {
  BLEScan *scanner = BLEDevice::getScan();
  scanner->setActiveScan(true);
  BLEScanResults *results = scanner->start(scanDurationSeconds_, false);
  BLEAdvertisedDevice *match = nullptr;
  if (results) {
    for (int index = 0; index < results->getCount(); ++index) {
      BLEAdvertisedDevice device = results->getDevice(index);
      String found = device.getAddress().toString();
      found.toLowerCase();
      if (found == peerMac_) {
        match = new BLEAdvertisedDevice(device);
        break;
      }
    }
  }
  scanner->clearResults();
  if (!match) return false;
  if (!client_) {
    client_ = BLEDevice::createClient();
    client_->setClientCallbacks(new ClientCallbacks());
  }
  const bool linked = client_->connect(match);
  delete match;
  if (!linked) return false;
  client_->setMTU(517);
  BLERemoteService *service = client_->getService(serviceUuid_);
  if (!service) { client_->disconnect(); return false; }
  downlink_ = service->getCharacteristic(downlinkUuid_);
  uplink_ = service->getCharacteristic(uplinkUuid_);
  if (!downlink_ || !uplink_ || !downlink_->canNotify() ||
      !uplink_->canWrite()) {
    client_->disconnect();
    return false;
  }
  downlink_->registerForNotify(notificationCallback);
  return true;
}
