#pragma once

// Safe provisioning defaults. Put real values in iris_secrets.local.h; runtime
// updates are stored in ESP32 NVS.
namespace IrisSecrets {
#if __has_include("iris_secrets.local.h")
#include "iris_secrets.local.h"
#else
constexpr char WIFI_SSID[] = "";
constexpr char WIFI_PASSWORD[] = "";
#endif
}
