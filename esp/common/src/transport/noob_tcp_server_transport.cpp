#include "transport/noob_tcp_server_transport.h"

TcpServerTransport::TcpServerTransport(uint16_t port, size_t maximumLine)
    : server_(port), maximumLine_(maximumLine) {}

#if defined(ESP32)
TcpServerTransport::TcpServerTransport(const IPAddress &bindAddress,
                                       uint16_t port, size_t maximumLine)
    : server_(bindAddress, port), maximumLine_(maximumLine) {}
#endif

bool TcpServerTransport::begin() {
  server_.begin();
  return static_cast<bool>(server_);
}

const char *TcpServerTransport::name() const { return "tcp-server"; }

bool TcpServerTransport::receive(String &message) {
  if (server_.hasClient()) {
    // A new command connection takes over immediately. Waiting for the old
    // TCP close event can leave one-shot clients connected but unanswered.
    client_.stop();
    input_ = "";
    discarding_ = false;
    client_ = server_.available();
  } else if (!client_ || !client_.connected()) {
    client_.stop();
    input_ = "";
    discarding_ = false;
  }
  if (!client_) return false;
  for (uint16_t consumed = 0; client_.available() && consumed < 128; ++consumed) {
    const char value = static_cast<char>(client_.read());
    if (value == '\n' || value == '\r') {
      if (discarding_) {
        discarding_ = false;
        continue;
      }
      if (!input_.isEmpty()) {
        message = input_;
        input_ = "";
        return true;
      }
    } else if (!discarding_) {
      if (input_.length() < maximumLine_) input_ += value;
      else {
        input_ = "";
        discarding_ = true;
      }
    }
  }
  return false;
}

void TcpServerTransport::send(const String &message) {
  if (client_ && client_.connected()) client_.println(message);
}
