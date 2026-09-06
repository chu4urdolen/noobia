#pragma once

// Provision locally before compiling. Runtime updates are stored in ESP32 NVS.
// Never commit a real network password here.
namespace IrisSecrets {
constexpr char WIFI_SSID[] = "Noobia";
constexpr char WIFI_PASSWORD[] = "";
}
