#include <Arduino.h>
#include <esp_heap_caps.h>
#include <esp_log.h>
#include <noob_usb_net.h>
#include <noob_runtime.h>
#include <services/Esp32WifiService.h>
#include <transport/noob_tcp_server_transport.h>
#include "src/noobs/iris/iris.h"
#include "src/noobs/iris/iris_config.h"
#include "src/noobs/iris/iris_usb_config.h"
#include "src/noobs/iris/nexus_peer_config.h"

namespace {
NoobRuntime runtime("Iris", "0.7.3-usb-control");
StreamTransport serialTransport("uart", Serial);
TcpServerTransport usbControl(
    IPAddress(IrisUsbNet::IP[0], IrisUsbNet::IP[1], IrisUsbNet::IP[2],
              IrisUsbNet::IP[3]),
    IrisUsbNet::CONTROL_PORT);
#if IRIS_ENABLE_BLE
BleClientTransport bleTransport(
    NexusPeer::BLE_MAC, NexusPeer::SERVICE_UUID, NexusPeer::DOWNLINK_UUID,
    NexusPeer::UPLINK_UUID, NexusPeer::RETRY_INTERVAL_MS,
    NexusPeer::SCAN_DURATION_SECONDS);
#endif

bool startUsbNetwork() {
  // Iris's Wi-Fi service already owns STA. Only add a USB LAN here; creating a
  // second bridge STA would steal Wi-Fi from Iris's native functions.
  esp_netif_ip_info_t lan = {};
  IP4_ADDR(&lan.ip, IrisUsbNet::IP[0], IrisUsbNet::IP[1],
           IrisUsbNet::IP[2], IrisUsbNet::IP[3]);
  lan.gw = lan.ip;
  IP4_ADDR(&lan.netmask, 255, 255, 255, 0);
  esp_netif_dns_info_t dns = {};
  dns.ip.type = ESP_IPADDR_TYPE_V4;
  IP4_ADDR(&dns.ip.u_addr.ip4, IrisUsbNet::FALLBACK_DNS[0],
           IrisUsbNet::FALLBACK_DNS[1], IrisUsbNet::FALLBACK_DNS[2],
           IrisUsbNet::FALLBACK_DNS[3]);
  const esp_err_t err = noob_usb_net_start(&lan, &dns);
  if (err != ESP_OK) ESP_LOGE("iris_usb", "USB LAN: %s", esp_err_to_name(err));
  return err == ESP_OK;
}

void logInternalHeap(const char *stage) {
  Serial.printf("NRP/1 0 EVENT HEAP stage=%s internal=%u\n", stage,
                static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL)));
}
}  // namespace

extern "C" void app_main(void) {
  initArduino();
  Serial.begin(115200);
  runtime.addTransport(serialTransport);
  logInternalHeap("arduino");
  const bool ready = irisRegister(runtime);
  logInternalHeap("iris");
#if IRIS_ENABLE_BLE
  Serial.println("NRP/1 0 EVENT INIT service=BLE");
  if (bleTransport.begin("Iris")) runtime.addTransport(bleTransport);
  Serial.println("NRP/1 0 EVENT INIT_DONE service=BLE");
  logInternalHeap("ble");
#endif
  Serial.println("NRP/1 0 EVENT INIT service=USB_NET");
  const bool usbReady = startUsbNetwork();
  Serial.println("NRP/1 0 EVENT INIT_DONE service=USB_NET");
  logInternalHeap("usb_net");
  if (usbReady && usbControl.begin() && runtime.addTransport(usbControl)) {
    runtime.capabilities().add("USB_NRP");
    Serial.printf("NRP/1 0 EVENT USB_CONTROL port=%u ready=1\n",
                  IrisUsbNet::CONTROL_PORT);
  } else {
    Serial.printf("NRP/1 0 EVENT USB_CONTROL port=%u ready=0\n",
                  IrisUsbNet::CONTROL_PORT);
  }
  const bool wifiAutoConnect = Esp32WifiService::startAutoConnect();
  Serial.printf("NRP/1 0 EVENT WIFI_AUTOCONNECT started=%d\n", wifiAutoConnect);
  Serial.println(ready ? "NRP/1 0 EVENT READY name=Iris"
                       : "NRP/1 0 EVENT DEGRADED name=Iris");
  for (;;) {
    runtime.loop();
    delay(1);
  }
}
