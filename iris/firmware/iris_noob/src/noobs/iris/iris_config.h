#pragma once

// Board service switches; disabled services are not registered.
#ifndef IRIS_ENABLE_CAMERA
#define IRIS_ENABLE_CAMERA 1
#endif
#ifndef IRIS_ENABLE_SD
#define IRIS_ENABLE_SD 1
#endif
#ifndef IRIS_ENABLE_MIC
#define IRIS_ENABLE_MIC 1
#endif
#ifndef IRIS_ENABLE_WIFI
#define IRIS_ENABLE_WIFI 1
#endif
#ifndef IRIS_ENABLE_BLE
#define IRIS_ENABLE_BLE 1
#endif
#ifndef IRIS_ENABLE_GPIO_DIAGNOSTICS
#define IRIS_ENABLE_GPIO_DIAGNOSTICS 0
#endif
#ifndef IRIS_ENABLE_IR
#define IRIS_ENABLE_IR 1
#endif

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
constexpr int IR_TX = 40;
constexpr int IR_RX = 18;
constexpr int DHT11_DATA = 15;
constexpr int PHOTORESISTOR = 1;
constexpr int ULTRASONIC_TRIG = 16;
constexpr int ULTRASONIC_ECHO = 48;
constexpr int EXTERNAL_LED_0 = 47;
constexpr int EXTERNAL_LED_2 = 17;

// MSM261D3526H1CPM digital microphone. Although the part is marketed as a
// PDM microphone, this board wires it to the ESP32-S3 as standard I2S: the
// narrow hardware probe produced centered 32-bit audio with these signals.
constexpr int MIC_DATA = 35;
constexpr int MIC_BCLK = 36;
constexpr int MIC_WS = 37;
constexpr int RGB_LED = 33;
constexpr int SIGNAL_LED = 34;
}

namespace IrisHardware {
constexpr uint32_t CAMERA_XCLK_HZ = 10000000;
constexpr int CAMERA_JPEG_QUALITY = 12;
constexpr int CAMERA_FRAME_BUFFERS = 2;
constexpr char SD_MOUNT[] = "/sdcard";
constexpr char CAPTURE_DIRECTORY[] = "/captured";
constexpr char CAPTURE_PREFIX[] = "capture_";
constexpr uint32_t IR_CARRIER_HZ = 38000;
constexpr uint32_t IR_SAMPLE_INTERVAL_US = 25;
constexpr uint32_t IR_LOOPBACK_BURST_US = 1000;
constexpr uint32_t IR_LOOPBACK_PAUSE_MS = 2;
constexpr uint8_t IR_PWM_RESOLUTION_BITS = 8;
constexpr uint32_t IR_PWM_DUTY = 128;
constexpr uint32_t ULTRASONIC_SETTLE_US = 2;
constexpr uint32_t ULTRASONIC_PULSE_US = 10;
constexpr uint32_t ULTRASONIC_INTER_SAMPLE_MS = 60;
constexpr uint32_t ULTRASONIC_SOUND_SPEED_MM_S = 343000;
constexpr uint8_t ULTRASONIC_DEFAULT_SAMPLES = 3;
constexpr uint32_t ULTRASONIC_DEFAULT_TIMEOUT_US = 30000;
constexpr uint32_t ULTRASONIC_CHANGE_INTERVAL_MS = 250;
constexpr int32_t ULTRASONIC_CHANGE_THRESHOLD_MM = 100;
constexpr uint8_t ULTRASONIC_CHANGE_REARM_SAMPLES = 4;
constexpr uint32_t POLICE_STEP_MS = 200;
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
constexpr unsigned LED_EXTERNAL = 132;
constexpr unsigned VM_SAVE = 140;
constexpr unsigned VM_LOAD_SAVED = 141;
constexpr unsigned VM_LIST_SAVED = 142;
constexpr unsigned VM_DELETE_SAVED = 143;
constexpr unsigned BLE_SCAN = 160;
constexpr unsigned BLE_PEER_SET = 161;
constexpr unsigned BLE_STATUS = 162;
constexpr unsigned GPIO_AUDIT = 170;
constexpr unsigned GPIO_INSPECT = 171;
constexpr unsigned GPIO_PULL_TEST = 172;
constexpr unsigned TEMP_HUMIDITY_READ = 190;
constexpr unsigned ADC_READ = 191;
constexpr unsigned LIGHT_READ = 192;
constexpr unsigned IR_SEND = 193;
constexpr unsigned IR_READ = 194;
constexpr unsigned IR_LOOPBACK = 195;
constexpr unsigned ULTRASONIC_READ = 196;
constexpr unsigned LED_BLUE = 197;
constexpr unsigned LED_RED = 198;
constexpr unsigned DISTANCE_MM = 199;
constexpr unsigned BLUE_BLINK_SEQUENCE = 200;
constexpr unsigned POLICE_SEQUENCE = 201;
constexpr unsigned ULTRASONIC_CHANGE_START = 202;
constexpr unsigned ULTRASONIC_CHANGE_STOP = 203;
constexpr unsigned ULTRASONIC_CHANGE_STATUS = 204;
constexpr unsigned ULTRASONIC_CHANGE_POP = 205;
constexpr unsigned ULTRASONIC_CHANGE_POLL = 206;
}
