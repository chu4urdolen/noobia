#include "transport/BleClientTransport.h"
#include <BLEDevice.h>
#include <BLEScan.h>

namespace {
BleClientTransport *activeTransport = nullptr;
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
  return mac.length() == 17 && mac != "00:00:00:00:00:00";
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
  if (!macConfigured(peerMac_)) return false;
  BLEDevice::init(localName ? localName : "Noob");
  activeTransport = this;
  initialized_ = true;
  nextAttemptAt_ = millis();
  return true;
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
