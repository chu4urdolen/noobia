#include "iris.h"
#include "iris_config.h"

void irisRegisterCapabilities(CapabilityRegistry &capabilities) {
#if IRIS_ENABLE_GPIO_DIAGNOSTICS
  capabilities.add("GPIO_DIAGNOSTICS");
#endif
  capabilities.add("EXTERNAL_LEDS");
  capabilities.add("DHT11");
  capabilities.add("ADC");
  capabilities.add("LIGHT_SENSOR");
  capabilities.add("ULTRASONIC");
  capabilities.add("LED_SEQUENCES");
  capabilities.add("ULTRASONIC_CHANGE_THREAD");
#if IRIS_ENABLE_IR
  capabilities.add("IR_TX");
  capabilities.add("IR_RX");
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
