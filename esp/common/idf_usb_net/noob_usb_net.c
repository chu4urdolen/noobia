/*
 * USB Ethernet netif for Noobs, adapted from Espressif esp-iot-bridge's
 * bridge_usb.c (Apache-2.0, copyright 2022 Espressif Systems).
 *
 * This deliberately omits the bridge's Wi-Fi management, web server,
 * provisioning, modem support, and netif registry. Iris owns her Wi-Fi
 * connection through the reusable Noob Wi-Fi service.
 */
#include "noob_usb_net.h"

#include <stdlib.h>
#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif_net_stack.h"
#include "esp_wifi.h"
#include "apps/dhcpserver/dhcpserver.h"
#include "lwip/etharp.h"
#include "lwip/ethip6.h"
#include "lwip/pbuf.h"
#include "lwip/snmp.h"
#include "tinyusb.h"
#include "tinyusb_default_config.h"
#include "tinyusb_net.h"

static const char *TAG = "noob_usb_net";
static esp_netif_t *usb_netif;
static esp_netif_dns_info_t default_dns;


// esp_netif's vanilla lwIP stack config is intentionally opaque in IDF.
struct noob_usb_lwip_stack {
    err_t (*init_fn)(struct netif *);
    void (*input_fn)(void *, void *, size_t, void *);
};

static esp_err_t usb_recv(void *buffer, uint16_t len, void *ctx)
{
    (void)ctx;
    return usb_netif ? esp_netif_receive(usb_netif, buffer, len, NULL) : ESP_ERR_INVALID_STATE;
}

static err_t usb_output(struct netif *netif, struct pbuf *packet)
{
    esp_netif_t *iface = esp_netif_get_handle_from_netif_impl(netif);
    if (!iface) return ERR_IF;
    struct pbuf *owned = NULL;
    if (packet->next) {
        owned = pbuf_alloc(PBUF_RAW_TX, packet->tot_len, PBUF_RAM);
        if (!owned) return ERR_MEM;
        if (pbuf_copy(owned, packet) != ERR_OK) {
            pbuf_free(owned);
            return ERR_IF;
        }
        packet = owned;
    }
    esp_err_t result = esp_netif_transmit(iface, packet->payload, packet->len);
    if (owned) pbuf_free(owned);
    return result == ESP_OK ? ERR_OK : (result == ESP_ERR_NO_MEM ? ERR_MEM : ERR_IF);
}

static void usb_input(void *handle, void *buffer, size_t len, void *rx_buffer)
{
    struct netif *netif = handle;
    esp_netif_t *iface = esp_netif_get_handle_from_netif_impl(netif);
    if (!buffer || !netif_is_up(netif)) {
        if (rx_buffer) esp_netif_free_rx_buffer(iface, rx_buffer);
        return;
    }
    struct pbuf *packet = pbuf_alloc(PBUF_RAW, len, PBUF_RAM);
    if (!packet) {
        if (rx_buffer) esp_netif_free_rx_buffer(iface, rx_buffer);
        return;
    }
    err_t copied = pbuf_take(packet, buffer, len);
    if (rx_buffer) esp_netif_free_rx_buffer(iface, rx_buffer);
    if (copied != ERR_OK ||
        netif->input(packet, netif) != ERR_OK) pbuf_free(packet);
}

static err_t usb_init(struct netif *netif)
{
    netif->name[0] = 'n';
    netif->name[1] = 'u';
    netif->hwaddr_len = ETHARP_HWADDR_LEN;
    netif->mtu = 1500;
    netif->flags = NETIF_FLAG_BROADCAST | NETIF_FLAG_ETHARP | NETIF_FLAG_LINK_UP;
    netif->output = etharp_output;
#if LWIP_IPV6
    netif->output_ip6 = ethip6_output;
#endif
    netif->linkoutput = usb_output;
    NETIF_INIT_SNMP(netif, snmp_ifType_ethernet_csmacd, 100);
    return ERR_OK;
}

static esp_err_t usb_transmit(void *handle, void *buffer, size_t len)
{
    (void)handle;
    return tinyusb_net_send_sync(buffer, len, NULL, pdMS_TO_TICKS(500));
}

static esp_err_t usb_transmit_wrap(void *handle, void *buffer, size_t len,
                                   void *netstack_buffer)
{
    (void)netstack_buffer;
    return usb_transmit(handle, buffer, len);
}

static void usb_free_rx(void *handle, void *buffer)
{
    (void)handle;
    free(buffer);
}

static esp_netif_driver_ifconfig_t usb_driver = {
    .handle = "noob-usb",
    .transmit = usb_transmit,
    .transmit_wrap = usb_transmit_wrap,
    .driver_free_rx_buffer = usb_free_rx,
};

static const struct noob_usb_lwip_stack usb_stack = {
    .init_fn = usb_init,
    .input_fn = usb_input,
};

static void wifi_got_ip(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)base;
    (void)id;
    if (!usb_netif) return;
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_dns_info_t dns = default_dns;
    if (sta && esp_netif_get_dns_info(sta, ESP_NETIF_DNS_MAIN, &dns) == ESP_OK &&
        dns.ip.u_addr.ip4.addr != 0) {
        esp_netif_set_dns_info(usb_netif, ESP_NETIF_DNS_MAIN, &dns);
    }
    (void)data;
}

esp_err_t noob_usb_net_start(const esp_netif_ip_info_t *lan_ip,
                             const esp_netif_dns_info_t *fallback_dns)
{
    if (usb_netif) return ESP_ERR_INVALID_STATE;
    if (!lan_ip || !fallback_dns) return ESP_ERR_INVALID_ARG;
    default_dns = *fallback_dns;

    const esp_netif_inherent_config_t inherent = {
        .flags = ESP_NETIF_DHCP_SERVER | ESP_NETIF_FLAG_GARP,
        .if_key = "NOOB_USB",
        .if_desc = "Noob USB LAN",
    };
    const esp_netif_config_t config = {
        .base = &inherent,
        .driver = &usb_driver,
        .stack = (const esp_netif_netstack_config_t *)&usb_stack,
    };
    esp_netif_t *iface = esp_netif_new(&config);
    if (!iface) return ESP_ERR_NO_MEM;
    usb_netif = iface;
    esp_netif_dhcps_stop(iface);
    esp_err_t err = esp_netif_set_ip_info(iface, lan_ip);
    uint8_t mac[6];
    if (err == ESP_OK) err = esp_read_mac(mac, ESP_MAC_WIFI_STA);
    // Give USB a stable locally administered MAC, distinct from Wi-Fi STA.
    if (err == ESP_OK) {
        mac[0] = (mac[0] | 0x02) & 0xfe;
        mac[5] ^= 0x01;
    }
    if (err == ESP_OK) err = esp_netif_set_mac(iface, mac);
    if (err != ESP_OK) goto fail;
    esp_netif_action_start(iface, NULL, 0, NULL);
    esp_netif_action_connected(iface, NULL, 0, NULL);
    dhcps_offer_t offer_dns = OFFER_DNS;
    err = esp_netif_dhcps_option(iface, ESP_NETIF_OP_SET,
                                 ESP_NETIF_DOMAIN_NAME_SERVER, &offer_dns,
                                 sizeof(offer_dns));
    if (err == ESP_OK) err = esp_netif_set_dns_info(iface, ESP_NETIF_DNS_MAIN, &default_dns);
    if (err != ESP_OK) goto fail;
    err = esp_netif_dhcps_start(iface);
    if (err != ESP_OK) goto fail;

    const tinyusb_config_t usb_config = TINYUSB_DEFAULT_CONFIG();
    err = tinyusb_driver_install(&usb_config);
    if (err != ESP_OK) goto fail;
    ESP_LOGI(TAG, "USB driver installed");
    tinyusb_net_config_t net_config = {.on_recv_callback = usb_recv};
    memcpy(net_config.mac_addr, mac, sizeof(mac));
    err = tinyusb_net_init(&net_config);
    if (err != ESP_OK) goto fail;
    ESP_LOGI(TAG, "USB network class initialized");
    err = esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                     wifi_got_ip, NULL);
    if (err != ESP_OK) goto fail;
    ESP_LOGI(TAG, "Wi-Fi IP event handler registered");
#if CONFIG_LWIP_IPV4_NAPT
    err = esp_netif_napt_enable(iface);
    if (err != ESP_OK) goto fail;
    ESP_LOGI(TAG, "USB NAT enabled");
#else
    err = ESP_ERR_NOT_SUPPORTED;
    goto fail;
#endif
    ESP_LOGI(TAG, "USB LAN ready: " IPSTR, IP2STR(&lan_ip->ip));
    return ESP_OK;

fail:
    ESP_LOGE(TAG, "USB LAN initialization failed: %s", esp_err_to_name(err));
    // TinyUSB has no safe in-place teardown here. Leave the netif addressable
    // for diagnosis; a reboot starts from a clean state.
    return err;
}

esp_netif_t *noob_usb_net_handle(void)
{
    return usb_netif;
}
