#pragma once

#include "esp_err.h"
#include "esp_netif.h"

#ifdef __cplusplus
extern "C" {
#endif

// Add a USB LAN to the existing ESP32 network stack. Wi-Fi remains owned by
// the Noob's Wi-Fi service; this module never starts or configures the radio.
esp_err_t noob_usb_net_start(const esp_netif_ip_info_t *lan_ip,
                             const esp_netif_dns_info_t *fallback_dns);
esp_netif_t *noob_usb_net_handle(void);

#ifdef __cplusplus
}
#endif
