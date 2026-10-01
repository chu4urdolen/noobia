#pragma once

#include <stdint.h>

// Iris's private USB LAN for the NanoPi. Wi-Fi credentials stay in the
// existing Iris Wi-Fi service and can still be changed through Noob commands.
namespace IrisUsbNet {
constexpr uint8_t IP[4] = {192, 168, 77, 1};
constexpr uint8_t FALLBACK_DNS[4] = {192, 168, 100, 1};
constexpr uint16_t CONTROL_PORT = 4242;
}
