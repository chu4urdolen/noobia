#include <Arduino.h>
#include <NoobRuntime.h>
#include "src/noobs/iris/iris.h"
#include "src/noobs/iris/nexus_peer_config.h"

NoobRuntime runtime("Iris", "0.1.0");
StreamTransport usbTransport("usb", Serial);
BleClientTransport bleTransport(
    NexusPeer::BLE_MAC, NexusPeer::SERVICE_UUID, NexusPeer::DOWNLINK_UUID,
    NexusPeer::UPLINK_UUID, NexusPeer::RETRY_INTERVAL_MS,
    NexusPeer::SCAN_DURATION_SECONDS);

void setup() {
  Serial.begin(115200);
  delay(1500);
  // BLE is preferred. UART/USB remains a recovery and development transport.
  if (bleTransport.begin("Iris")) runtime.addTransport(bleTransport);
  runtime.addTransport(usbTransport);
  const bool ready = irisRegister(runtime);
  Serial.println(ready ? "NRP/1 0 EVENT READY name=Iris"
                       : "NRP/1 0 EVENT DEGRADED name=Iris");
  Serial.println("NRP/1 0 EVENT BLE " + bleTransport.status());
}

void loop() {
  runtime.loop();
  delay(1);
}
