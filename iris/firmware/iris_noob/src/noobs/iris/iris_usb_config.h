#pragma once
#include <stdint.h>

// Neo boots more slowly than ESP; display requests retry without faulting VM.
constexpr uint32_t IRIS_NEO_DISPLAY_RETRY_MS = 10000;

// Iris's private USB LAN for the NanoPi. Wi-Fi credentials stay in the
// existing Iris Wi-Fi service and can still be changed through Noob commands.
namespace IrisUsbNet {
constexpr uint8_t IP[4] = {192, 168, 77, 1};
// Neo receives the first DHCP lease on Iris's private USB LAN.
constexpr uint8_t NEO_IP[4] = {192, 168, 77, 2};
constexpr uint8_t FALLBACK_DNS[4] = {192, 168, 100, 1};
constexpr uint16_t CONTROL_PORT = 4242;
constexpr uint16_t NEO_COMMAND_PORT = 4243;
}
