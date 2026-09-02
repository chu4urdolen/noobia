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
constexpr unsigned WIFI_SCAN = 110;
constexpr unsigned WIFI_RSSI = 111;
constexpr unsigned RSSI_ON = 112;
constexpr unsigned RSSI_OFF = 113;
constexpr unsigned MIC_LEVEL = 120;
constexpr unsigned MIC_ABOVE = 121;
constexpr unsigned LED_RGB = 130;
constexpr unsigned LED_SIGNAL = 131;
}
