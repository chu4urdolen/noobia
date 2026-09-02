#pragma once
#include "transport/Transport.h"
#include <BLEClient.h>

// Reusable outbound BLE transport. A Noob supplies peer identity and retry
// policy; the runtime continues to consume ordinary NRP/1 message frames.
class BleClientTransport : public NoobTransport {
 public:
  BleClientTransport(const char *peerMac, const char *serviceUuid,
                     const char *downlinkUuid, const char *uplinkUuid,
                     uint32_t retryIntervalMs = 30000,
                     uint8_t scanDurationSeconds = 5);
  bool begin(const char *localName);
  const char *name() const override;
  bool receive(String &message) override;
  void send(const String &message) override;
  bool connected() const;
  String status() const;
  void handleNotification(const uint8_t *data, size_t length);
  void handleDisconnect();

 private:
  void maintainConnection();
  bool scanAndConnect();
  String peerMac_;
  BLEUUID serviceUuid_, downlinkUuid_, uplinkUuid_;
  BLEClient *client_ = nullptr;
  BLERemoteCharacteristic *downlink_ = nullptr;
  BLERemoteCharacteristic *uplink_ = nullptr;
  String pendingFrame_;
  uint32_t retryIntervalMs_, nextAttemptAt_ = 0;
  uint8_t scanDurationSeconds_;
  bool initialized_ = false;
};
