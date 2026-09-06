#pragma once

namespace IrisPins {
constexpr int CAMERA_SDA = 21;
constexpr int CAMERA_SCL = 14;
constexpr int CAMERA_VSYNC = 13;
constexpr int CAMERA_HREF = 12;
constexpr int CAMERA_D0 = 5;
constexpr int CAMERA_D1 = 3;
constexpr int CAMERA_D2 = 2;
constexpr int CAMERA_D3 = 4;
constexpr int CAMERA_D4 = 6;
constexpr int CAMERA_D5 = 8;
constexpr int CAMERA_D6 = 9;
constexpr int CAMERA_D7 = 11;
constexpr int CAMERA_PCLK = 7;
constexpr int CAMERA_XCLK = 10;
constexpr int SD_CLK = 42;
constexpr int SD_CMD = 39;
constexpr int SD_D0 = 41;
constexpr int I2C_SDA = 1;
constexpr int I2C_SCL = 40;

// MSM261D3526H1CPM digital microphone. Although the part is marketed as a
// PDM microphone, this board wires it to the ESP32-S3 as standard I2S: the
// narrow hardware probe produced centered 32-bit audio with these signals.
constexpr int MIC_DATA = 35;
constexpr int MIC_BCLK = 36;
constexpr int MIC_WS = 37;
constexpr int RGB_LED = 33;
constexpr int SIGNAL_LED = 34;
}

namespace IrisFunctions {
constexpr unsigned CAMERA_CAPTURE = 100;
constexpr unsigned STORAGE_STATUS = 101;
constexpr unsigned SD_LIST = 102;
constexpr unsigned SD_READ_CHUNK = 103;
constexpr unsigned SD_DELETE = 104;
constexpr unsigned SD_DELETE_PATH = 105;
constexpr unsigned SD_LIST_PATH = 106;
constexpr unsigned CAMERA_VIDEO = 107;
constexpr unsigned WIFI_SCAN = 110;
constexpr unsigned WIFI_RSSI = 111;
constexpr unsigned RSSI_ON = 112;
constexpr unsigned RSSI_OFF = 113;
constexpr unsigned WIFI_CONNECT = 114;
constexpr unsigned WIFI_DISCONNECT = 115;
constexpr unsigned WIFI_STATUS = 116;
constexpr unsigned WIFI_CREDENTIALS_SET = 117;
constexpr unsigned MIC_LEVEL = 120;
constexpr unsigned MIC_ABOVE = 121;
constexpr unsigned AUDIO_RECORD = 122;
constexpr unsigned LED_RGB = 130;
constexpr unsigned LED_SIGNAL = 131;
constexpr unsigned VM_SAVE = 140;
constexpr unsigned VM_LOAD_SAVED = 141;
constexpr unsigned VM_LIST_SAVED = 142;
constexpr unsigned VM_DELETE_SAVED = 143;
constexpr unsigned I2C_SCAN = 150;
constexpr unsigned I2C_WRITE = 151;
constexpr unsigned I2C_READ = 152;
constexpr unsigned I2C_WRITE_READ = 153;
constexpr unsigned I2C_SOFT_SCAN = 154;
constexpr unsigned BLE_SCAN = 160;
constexpr unsigned BLE_PEER_SET = 161;
constexpr unsigned BLE_STATUS = 162;
constexpr unsigned GPIO_AUDIT = 170;
constexpr unsigned GPIO_INSPECT = 171;
constexpr unsigned GPIO_PULL_TEST = 172;
constexpr unsigned OLED_TEST = 180;
}
