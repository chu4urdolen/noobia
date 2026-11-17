#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <noob_runtime.h>

#include "src/lolth.h"
#include "src/lolth_ap.h"

namespace {
NoobRuntime runtime("Lolth", "0.1.0");
TcpServerTransport wifiTransport(4242);
}

void setup() {
  // LAFVIN wires the ultrasonic trigger/echo to UART TX/RX. Do not start
  // Serial: the sensor and USB serial share these pins.
  lolthBeginSensor();
  lolthRegister(runtime);
  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  const IPAddress apIp(LolthAp::IP[0], LolthAp::IP[1],
                       LolthAp::IP[2], LolthAp::IP[3]);
  const IPAddress subnet(LolthAp::SUBNET[0], LolthAp::SUBNET[1],
                         LolthAp::SUBNET[2], LolthAp::SUBNET[3]);
  WiFi.softAPConfig(apIp, apIp, subnet);
  WiFi.softAP(LolthAp::SSID, LolthAp::PASSWORD);
  wifiTransport.begin();
  runtime.addTransport(wifiTransport);
}

void loop() {
  runtime.loop();
  delay(1);
}
