#include "iris.h"
#include "iris_config.h"

void irisRegisterCapabilities(CapabilityRegistry &capabilities) {
#if IRIS_ENABLE_GPIO_DIAGNOSTICS
  capabilities.add("GPIO_DIAGNOSTICS");
#endif
#if IRIS_ENABLE_I2C
  capabilities.add("I2C");
#endif
  capabilities.add("EXTERNAL_LEDS");
  capabilities.add("DHT11");
#if IRIS_ENABLE_OLED
  capabilities.add("OLED_SH1107_128X128");
#endif
  capabilities.add("UART");
  capabilities.add("VM");
#if IRIS_ENABLE_WIFI
  capabilities.add("WIFI");
#endif
#if IRIS_ENABLE_BLE
  capabilities.add("BLE");
#endif
#if IRIS_ENABLE_CAMERA
  capabilities.add("CAMERA");
#endif
#if IRIS_ENABLE_SD
  capabilities.add("SD");
  capabilities.add("VM_STORE");
#endif
#if IRIS_ENABLE_MIC
  capabilities.add("MIC");
#endif
  capabilities.add("RGB_LED");
  capabilities.add("SIGNAL_LED");
}
