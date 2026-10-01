#pragma once
#include "transport/noob_transport.h"
#include "syscalls/noob_native_registry.h"
#if defined(NOOB_USE_NIMBLE)
#include <NimBLEDevice.h>
#else
#include <BLEClient.h>
class BLEAdvertisedDevice;
class BLEScanResults;
#endif

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
  static NativeResult scan(const int32_t *arguments, uint8_t argumentCount);
  static NativeResult setPeer(const String &arguments);
  static NativeResult nativeStatus(const int32_t *arguments,
                                   uint8_t argumentCount);
  void handleNotification(const uint8_t *data, size_t length);
  void handleDisconnect();
#if defined(NOOB_USE_NIMBLE)
  void handleAdvertisement(const NimBLEAdvertisedDevice *device);
  void handleScanComplete(const NimBLEScanResults &results, int reason);
#else
  void handleAdvertisement(BLEAdvertisedDevice device);
  void handleScanComplete(BLEScanResults results);
#endif

 private:
  void maintainConnection();
  bool startScan();
  bool connectMatch();
  String peerMac_;
#if defined(NOOB_USE_NIMBLE)
  NimBLEUUID serviceUuid_, downlinkUuid_, uplinkUuid_;
  NimBLEClient *client_ = nullptr;
#else
  BLEUUID serviceUuid_, downlinkUuid_, uplinkUuid_;
  BLEClient *client_ = nullptr;
#endif
  bool pendingMatch_ = false;
  uint8_t pendingAddressType_ = 0xFF;
#if defined(NOOB_USE_NIMBLE)
  NimBLERemoteCharacteristic *downlink_ = nullptr;
  NimBLERemoteCharacteristic *uplink_ = nullptr;
#else
  BLERemoteCharacteristic *downlink_ = nullptr;
  BLERemoteCharacteristic *uplink_ = nullptr;
#endif
  String pendingFrame_;
  uint32_t retryIntervalMs_, nextAttemptAt_ = 0;
  uint8_t scanDurationSeconds_;
  bool initialized_ = false;
  bool scanRunning_ = false;
};
