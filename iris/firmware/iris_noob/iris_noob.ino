#include <Arduino.h>
#include <NoobRuntime.h>
#include "src/noobs/iris/iris.h"
#include "src/noobs/iris/iris_config.h"
#include "src/noobs/iris/nexus_peer_config.h"

NoobRuntime runtime("Iris", "0.4.0");
StreamTransport usbTransport("usb", Serial);
#if IRIS_ENABLE_BLE
BleClientTransport bleTransport(
    NexusPeer::BLE_MAC, NexusPeer::SERVICE_UUID, NexusPeer::DOWNLINK_UUID,
    NexusPeer::UPLINK_UUID, NexusPeer::RETRY_INTERVAL_MS,
    NexusPeer::SCAN_DURATION_SECONDS);
#endif

void setup() {
  Serial.begin(115200);
  delay(1500);
  runtime.addTransport(usbTransport);
  Serial.printf("NRP/1 0 EVENT BOOT flash=%u psram=%u\n",
                ESP.getFlashChipSize(), ESP.getPsramSize());
  const bool ready = irisRegister(runtime);
#if IRIS_ENABLE_BLE
  Serial.println("NRP/1 0 EVENT INIT service=BLE");
  if (bleTransport.begin("Iris")) runtime.addTransport(bleTransport);
#endif
  Serial.println(ready ? "NRP/1 0 EVENT READY name=Iris"
                       : "NRP/1 0 EVENT DEGRADED name=Iris");
#if IRIS_ENABLE_BLE
  Serial.println("NRP/1 0 EVENT BLE " + bleTransport.status());
#endif
}

void loop() {
  runtime.loop();
  delay(1);
}
