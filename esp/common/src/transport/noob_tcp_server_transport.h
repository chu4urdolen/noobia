#pragma once

#include "transport/noob_transport.h"

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#elif defined(ESP32)
#include <WiFi.h>
#endif

// A line-oriented NRP/1 server over Wi-Fi. The physical Noob chooses whether
// Wi-Fi runs as an access point or a station; this transport only owns TCP.
class TcpServerTransport : public NoobTransport {
 public:
  explicit TcpServerTransport(uint16_t port = 4242,
                              size_t maximumLine = 2200);
#if defined(ESP32)
  TcpServerTransport(const IPAddress &bindAddress, uint16_t port,
                     size_t maximumLine = 2200);
#endif
  bool begin();
  const char *name() const override;
  bool receive(String &message) override;
  void send(const String &message) override;

 private:
  WiFiServer server_;
  WiFiClient client_;
  String input_;
  const size_t maximumLine_;
  bool discarding_ = false;
};
