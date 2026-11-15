#pragma once

namespace NexusPeer {
// Nexus Realtek hci0 controller. Keep peer identity in Noob-specific
// configuration; the reusable BLE transport does not know who Nexus is.
constexpr char BLE_MAC[] = "00:E0:4C:23:99:87";
// Nexus hosts this service. DOWNLINK carries commands to Iris; UPLINK carries
// matching NRP/1 replies back to Nexus.
constexpr char SERVICE_UUID[] = "6e6f6f62-6961-4e45-5855-530000000001";
constexpr char DOWNLINK_UUID[] = "6e6f6f62-6961-4e45-5855-530000000002";
constexpr char UPLINK_UUID[] = "6e6f6f62-6961-4e45-5855-530000000003";
// Scan for five seconds every thirty seconds rather than thrashing the shared
// Wi-Fi/BLE radio in a tight reconnect loop.
constexpr unsigned RETRY_INTERVAL_MS = 30000;
constexpr unsigned SCAN_DURATION_SECONDS = 5;
}
