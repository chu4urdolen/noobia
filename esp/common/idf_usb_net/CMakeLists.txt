idf_component_register(
    SRCS "noob_usb_net.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_netif esp_wifi espressif__esp_tinyusb
    PRIV_REQUIRES lwip esp_event)
