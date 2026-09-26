#include "iris.h"
#include "iris_config.h"
#include "iris_secrets.h"
#include <transport/noob_ble_client_transport.h>
#include <services/Esp32WifiService.h>
#include <services/Esp32SdMmcService.h>
#include <services/Esp32CameraService.h>
#include <services/Esp32I2sMicService.h>
#include <services/Esp32RgbLedService.h>
#include <services/Esp32SignalLedService.h>
#include <services/Esp32DigitalOutputService.h>
#include <services/Esp32Dht11Service.h>
#include <services/Esp32AdcService.h>
#include <services/Esp32IrService.h>
#include <services/Esp32UltrasonicService.h>
#include <services/Esp32VmProgramStore.h>
#include "hw_artifacts.h"
#include "hw_functions.h"
#include "seq_leds.h"
#include "seq_media.h"
#include "thread_detectors.h"
#include "thread_ir_capture.h"
#include "thread_sampling.h"
#if IRIS_ENABLE_GPIO_DIAGNOSTICS
#include <Esp32GpioInspector.h>
#endif

void irisRegisterCapabilities(CapabilityRegistry &capabilities);

namespace {
NativeResult irisLightRead(const int32_t *arguments, uint8_t count) {
  if (count > 1) return {false, 0, "usage: [samples(1..64)]"};
  const int32_t args[] = {0, count ? arguments[0] : 16};
  return Esp32AdcService::read(args, 2);
}
bool initService(const char *name, bool (*begin)()) {
  Serial.printf("NRP/1 0 EVENT INIT service=%s\n", name);
  const bool ready = begin();
  Serial.printf("NRP/1 0 EVENT INIT_DONE service=%s ok=%d\n", name, ready);
  return ready;
}
NativeResult irisExternalLed(const int32_t *arguments, uint8_t count) {
  if (count != 2 || (arguments[0] != 0 && arguments[0] != 2) ||
      arguments[1] < 0 || arguments[1] > 1)
    return {false, 0, "usage: led(0=GPIO47|2=GPIO17) state(0|1)"};
  // Preserve channel IDs for the two LEDs still attached.
  const int pin = arguments[0] == 0 ? IrisPins::EXTERNAL_LED_0
                                  : IrisPins::EXTERNAL_LED_2;
  return Esp32DigitalOutputService::set(pin, arguments[1] != 0);
}
}

bool irisRegister(NoobRuntime &runtime) {
  // This is the single composition root for Iris. Common code learns what Iris
  // supports only through these registries, never through board-name checks.
  irisRegisterCapabilities(runtime.capabilities());
  bool ok = true;
  ok &= Esp32AdcService::configure(0, IrisPins::PHOTORESISTOR);
  ok &= runtime.natives().add(IrisFunctions::ADC_READ, "ADC_READ", Esp32AdcService::read);
  ok &= runtime.natives().add(IrisFunctions::LIGHT_READ, "LIGHT_READ", irisLightRead);
  ok &= Esp32UltrasonicService::begin({
      IrisPins::ULTRASONIC_TRIG, IrisPins::ULTRASONIC_ECHO,
      IrisHardware::ULTRASONIC_SETTLE_US, IrisHardware::ULTRASONIC_PULSE_US,
      IrisHardware::ULTRASONIC_INTER_SAMPLE_MS,
      IrisHardware::ULTRASONIC_SOUND_SPEED_MM_S,
      IrisHardware::ULTRASONIC_DEFAULT_SAMPLES,
      IrisHardware::ULTRASONIC_DEFAULT_TIMEOUT_US});
  ok &= runtime.natives().add(IrisFunctions::ULTRASONIC_READ,
                              "ULTRASONIC_READ",
                              Esp32UltrasonicService::measure);
  ok &= runtime.natives().add(IrisFunctions::DISTANCE_MM, "DISTANCE_MM",
                              irisDistanceFunction());
  ok &= Esp32Dht11Service::begin(IrisPins::DHT11_DATA);
  ok &= runtime.natives().add(IrisFunctions::TEMP_HUMIDITY_READ, "TEMP_HUMIDITY_READ", Esp32Dht11Service::read);
#if IRIS_ENABLE_IR
  ok &= Esp32IrService::begin({
      IrisPins::IR_TX, IrisPins::IR_RX, IrisHardware::IR_CARRIER_HZ,
      IrisHardware::IR_SAMPLE_INTERVAL_US, IrisHardware::IR_LOOPBACK_BURST_US,
      IrisHardware::IR_LOOPBACK_PAUSE_MS, IrisHardware::IR_PWM_RESOLUTION_BITS,
      IrisHardware::IR_PWM_DUTY, IrisHardware::IR_CAPTURE_RESOLUTION_HZ,
      IrisHardware::IR_CAPTURE_IDLE_US,
      IrisHardware::IR_CAPTURE_MIN_PULSE_US});
#endif
#if IRIS_ENABLE_CAMERA
  ok &= initService("CAMERA", irisCameraBegin);
#endif
#if IRIS_ENABLE_SD
  ok &= initService("SD", irisStorageBegin);
#endif
#if IRIS_ENABLE_MIC
  ok &= initService("MIC", irisMicrophoneBegin);
#endif
  ok &= Esp32RgbLedService::begin(IrisPins::RGB_LED);
  ok &= Esp32SignalLedService::begin(IrisPins::SIGNAL_LED);
#if IRIS_ENABLE_WIFI
  Serial.println("NRP/1 0 EVENT INIT service=WIFI");
  ok &= Esp32WifiService::begin(IrisSecrets::WIFI_SSID, IrisSecrets::WIFI_PASSWORD);
#endif
#if IRIS_ENABLE_SD
  ok &= Esp32VmProgramStore::begin(runtime.vm());
  runtime.setVmLifecycle(Esp32VmProgramStore::lifecycle());
#endif
#if IRIS_ENABLE_GPIO_DIAGNOSTICS
  ok &= Esp32GpioInspector::begin(48);
  const uint8_t cameraPins[] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 21};
  for (uint8_t pin : cameraPins) ok &= Esp32GpioInspector::reserve(pin, "camera");
  for (uint8_t pin = 26; pin <= 32; ++pin) ok &= Esp32GpioInspector::reserve(pin, "flash-psram");
  const uint8_t sdPins[] = {38, 39, 41, 42};
  for (uint8_t pin : sdPins) ok &= Esp32GpioInspector::reserve(pin, "sd");
  const uint8_t micPins[] = {35, 36, 37};
  for (uint8_t pin : micPins) ok &= Esp32GpioInspector::reserve(pin, "mic");
  ok &= Esp32GpioInspector::reserve(19, "usb-dminus");
  ok &= Esp32GpioInspector::reserve(20, "usb-dplus");
  ok &= Esp32GpioInspector::reserve(33, "rgb-led");
  ok &= Esp32GpioInspector::reserve(34, "signal-led");
  ok &= Esp32GpioInspector::reserve(43, "uart0-tx");
  ok &= Esp32GpioInspector::reserve(44, "uart0-rx");
  ok &= Esp32GpioInspector::reserve(0, "boot-strap");
  ok &= Esp32GpioInspector::reserve(45, "strap");
  ok &= Esp32GpioInspector::reserve(46, "strap-input-only");
  const uint8_t pullTestPins[] = {47, 48};
  for (uint8_t pin : pullTestPins) ok &= Esp32GpioInspector::allowPullTest(pin);
#endif

  // Iris selects capabilities and IDs here; every implementation below is a
  // reusable ESP32 service with no knowledge of the Iris board pin map.
#if IRIS_ENABLE_CAMERA
  ok &= runtime.natives().add(IrisFunctions::CAMERA_CAPTURE, "CAMERA_CAPTURE", Esp32CameraService::capture);
  ok &= runtime.natives().add(IrisFunctions::CAMERA_VIDEO, "CAMERA_VIDEO", Esp32CameraService::recordMjpeg);
#endif
#if IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::STORAGE_STATUS, "STORAGE_STATUS", Esp32SdMmcService::status);
  ok &= runtime.natives().add(IrisFunctions::SD_LIST, "CAPTURE_LIST", Esp32SdMmcService::list);
  ok &= runtime.natives().add(IrisFunctions::SD_READ_CHUNK, "CAPTURE_READ_CHUNK", Esp32SdMmcService::readChunk);
  ok &= runtime.natives().add(IrisFunctions::SD_DELETE, "CAPTURE_DELETE", Esp32SdMmcService::remove);
  ok &= runtime.natives().addText(IrisFunctions::SD_DELETE_PATH, "SD_DELETE", Esp32SdMmcService::removePath);
  ok &= runtime.natives().addText(IrisFunctions::SD_LIST_PATH, "SD_LIST", Esp32SdMmcService::listPath);
  ok &= runtime.natives().addText(IrisFunctions::SD_READ_PATH, "SD_READ",
                                  Esp32SdMmcService::readPathChunk);
#endif
#if IRIS_ENABLE_WIFI
  ok &= runtime.natives().add(IrisFunctions::WIFI_SCAN, "WIFI_SCAN", Esp32WifiService::scan);
  ok &= runtime.natives().add(IrisFunctions::WIFI_RSSI, "WIFI_RSSI", Esp32WifiService::rssi);
  ok &= runtime.natives().add(IrisFunctions::RSSI_ON, "RSSI_ON", Esp32WifiService::rssiOn);
  ok &= runtime.natives().add(IrisFunctions::RSSI_OFF, "RSSI_OFF", Esp32WifiService::rssiOff);
  ok &= runtime.natives().add(IrisFunctions::WIFI_CONNECT, "WIFI_CONNECT", Esp32WifiService::connect);
  ok &= runtime.natives().add(IrisFunctions::WIFI_DISCONNECT, "WIFI_DISCONNECT", Esp32WifiService::disconnect);
  ok &= runtime.natives().add(IrisFunctions::WIFI_STATUS, "WIFI_STATUS", Esp32WifiService::status);
  ok &= runtime.natives().addText(IrisFunctions::WIFI_CREDENTIALS_SET, "WIFI_CREDENTIALS_SET", Esp32WifiService::setCredentials);
#endif
#if IRIS_ENABLE_MIC
  ok &= runtime.natives().add(IrisFunctions::MIC_LEVEL, "MIC_LEVEL", Esp32I2sMicService::level);
  ok &= runtime.natives().add(IrisFunctions::MIC_ABOVE, "MIC_ABOVE", Esp32I2sMicService::above);
  ok &= runtime.natives().add(IrisFunctions::AUDIO_RECORD, "AUDIO_RECORD", Esp32I2sMicService::recordWav);
#endif
  ok &= runtime.natives().add(IrisFunctions::LED_RGB, "LED_RGB", Esp32RgbLedService::set);
  ok &= runtime.natives().add(IrisFunctions::LED_SIGNAL, "LED_SIGNAL", Esp32SignalLedService::set);
  ok &= runtime.natives().add(IrisFunctions::LED_EXTERNAL, "LED_EXTERNAL", irisExternalLed);
  ok &= runtime.natives().add(IrisFunctions::LED_BLUE, "LED_BLUE",
                              irisBlueLedFunction());
  ok &= runtime.natives().add(IrisFunctions::LED_RED, "LED_RED",
                              irisRedLedFunction());
  ok &= runtime.natives().add(IrisFunctions::BLUE_BLINK_SEQUENCE,
                              "BLUE_BLINK_SEQUENCE",
                              irisBlueBlinkSequence());
  ok &= runtime.natives().add(IrisFunctions::POLICE_SEQUENCE,
                              "POLICE_SEQUENCE", irisPoliceSequence());
#if IRIS_ENABLE_CAMERA && IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::CAMERA_SEQUENCE_STEP,
                              "CAMERA_SEQUENCE_STEP",
                              irisCameraSequenceStep);
  ok &= runtime.natives().add(IrisFunctions::CAMERA_SEQUENCE,
                              "CAMERA_SEQUENCE", irisCameraSequence());
#endif
#if IRIS_ENABLE_IR && IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::IR_SEQUENCE_STEP,
                              "IR_SEQUENCE_STEP", irisIrSequenceStep);
  ok &= runtime.natives().add(IrisFunctions::IR_SEQUENCE,
                              "IR_SEQUENCE", irisIrSequence());
#endif
#if IRIS_ENABLE_WIFI && IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::RSSI_SNAPSHOT,
                              "RSSI_SNAPSHOT", irisRssiSnapshot);
#endif
#if IRIS_ENABLE_IR && IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::IR_SNAPSHOT,
                              "IR_SNAPSHOT", irisIrSnapshot);
#endif
#if IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::ENV_SNAPSHOT,
                              "ENV_SNAPSHOT", irisEnvSnapshot);
  ok &= runtime.natives().add(IrisFunctions::ENV_TEMPERATURE,
                              "ENV_TEMPERATURE", irisEnvTemperature);
  ok &= runtime.natives().add(IrisFunctions::ENV_HUMIDITY,
                              "ENV_HUMIDITY", irisEnvHumidity);
#endif
  irisThreadsBegin(runtime.natives());
  irisSamplingThreadsBegin(runtime.natives());
  ok &= runtime.natives().add(IrisFunctions::ULTRASONIC_CHANGE_START,
                              "ULTRASONIC_CHANGE_START",
                              irisUltrasonicChangeThread());
  ok &= runtime.natives().add(IrisFunctions::ULTRASONIC_CHANGE_STOP,
                              "ULTRASONIC_CHANGE_STOP",
                              irisUltrasonicChangeStop());
  ok &= runtime.natives().add(IrisFunctions::ULTRASONIC_CHANGE_STATUS,
                              "ULTRASONIC_CHANGE_STATUS",
                              irisUltrasonicChangeStatus());
  ok &= runtime.natives().add(IrisFunctions::ULTRASONIC_CHANGE_POP,
                              "ULTRASONIC_CHANGE_POP",
                              irisUltrasonicChangePop());
  ok &= runtime.natives().add(IrisFunctions::ULTRASONIC_CHANGE_POLL,
                              "ULTRASONIC_CHANGE_POLL",
                              irisUltrasonicChangePoll());
  ok &= runtime.natives().add(IrisFunctions::LIGHT_CHANGE_START,
                              "LIGHT_CHANGE_START",
                              irisLightChangeThread());
  ok &= runtime.natives().add(IrisFunctions::LIGHT_CHANGE_STOP,
                              "LIGHT_CHANGE_STOP", irisLightChangeStop());
  ok &= runtime.natives().add(IrisFunctions::LIGHT_CHANGE_STATUS,
                              "LIGHT_CHANGE_STATUS", irisLightChangeStatus());
  ok &= runtime.natives().add(IrisFunctions::LIGHT_CHANGE_POP,
                              "LIGHT_CHANGE_POP", irisLightChangePop());
  ok &= runtime.natives().add(IrisFunctions::LIGHT_CHANGE_POLL,
                              "LIGHT_CHANGE_POLL", irisLightChangePoll());
#if IRIS_ENABLE_MIC
  ok &= runtime.natives().add(IrisFunctions::MIC_RISE_START,
                              "MIC_RISE_START", irisMicRiseThread());
  ok &= runtime.natives().add(IrisFunctions::MIC_RISE_STOP,
                              "MIC_RISE_STOP", irisMicRiseStop());
  ok &= runtime.natives().add(IrisFunctions::MIC_RISE_STATUS,
                              "MIC_RISE_STATUS", irisMicRiseStatus());
  ok &= runtime.natives().add(IrisFunctions::MIC_RISE_POP,
                              "MIC_RISE_POP", irisMicRisePop());
  ok &= runtime.natives().add(IrisFunctions::MIC_RISE_POLL,
                              "MIC_RISE_POLL", irisMicRisePoll());
#endif
#if IRIS_ENABLE_WIFI && IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::RSSI_THREAD_START,
                              "RSSI_THREAD_START", irisRssiThread());
  ok &= runtime.natives().add(IrisFunctions::RSSI_THREAD_STOP,
                              "RSSI_THREAD_STOP", irisRssiThreadStop());
  ok &= runtime.natives().add(IrisFunctions::RSSI_THREAD_STATUS,
                              "RSSI_THREAD_STATUS", irisRssiThreadStatus());
  ok &= runtime.natives().add(IrisFunctions::RSSI_THREAD_POP,
                              "RSSI_THREAD_POP", irisRssiThreadPop());
  ok &= runtime.natives().add(IrisFunctions::RSSI_THREAD_POLL,
                              "RSSI_THREAD_POLL", irisRssiThreadPoll());
  ok &= runtime.natives().add(IrisFunctions::RSSI_THREAD_FIELD,
                              "RSSI_THREAD_FIELD", irisRssiThreadField());
#endif
#if IRIS_ENABLE_IR && IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::IR_THREAD_START,
                              "IR_THREAD_START", irisIrThread());
  ok &= runtime.natives().add(IrisFunctions::IR_THREAD_STOP,
                              "IR_THREAD_STOP", irisIrThreadStop());
  ok &= runtime.natives().add(IrisFunctions::IR_THREAD_STATUS,
                              "IR_THREAD_STATUS", irisIrThreadStatus());
  ok &= runtime.natives().add(IrisFunctions::IR_THREAD_POP,
                              "IR_THREAD_POP", irisIrThreadPop());
  ok &= runtime.natives().add(IrisFunctions::IR_THREAD_POLL,
                              "IR_THREAD_POLL", irisIrThreadPoll());
  ok &= runtime.natives().add(IrisFunctions::IR_THREAD_FIELD,
                              "IR_THREAD_FIELD", irisIrThreadField());
  ok &= runtime.natives().addText(IrisFunctions::IR_DICT_REMEMBER,
                                  "IR_DICT_REMEMBER",
                                  irisIrDictionaryRemember);
  ok &= runtime.natives().add(IrisFunctions::IR_DICT_STATUS,
                              "IR_DICT_STATUS", irisIrDictionaryStatus);
#endif
#if IRIS_ENABLE_SD
  ok &= runtime.natives().add(IrisFunctions::ENV_THREAD_START,
                              "ENV_THREAD_START", irisEnvThread());
  ok &= runtime.natives().add(IrisFunctions::ENV_THREAD_STOP,
                              "ENV_THREAD_STOP", irisEnvThreadStop());
  ok &= runtime.natives().add(IrisFunctions::ENV_THREAD_STATUS,
                              "ENV_THREAD_STATUS", irisEnvThreadStatus());
  ok &= runtime.natives().add(IrisFunctions::ENV_THREAD_POP,
                              "ENV_THREAD_POP", irisEnvThreadPop());
  ok &= runtime.natives().add(IrisFunctions::ENV_THREAD_POLL,
                              "ENV_THREAD_POLL", irisEnvThreadPoll());
  ok &= runtime.natives().add(IrisFunctions::ENV_THREAD_FIELD,
                              "ENV_THREAD_FIELD", irisEnvThreadField());
#endif
#if IRIS_ENABLE_IR
  ok &= runtime.natives().add(IrisFunctions::IR_SEND, "IR_SEND", Esp32IrService::send);
  ok &= runtime.natives().add(IrisFunctions::IR_READ, "IR_READ", Esp32IrService::read);
  ok &= runtime.natives().add(IrisFunctions::IR_LOOPBACK, "IR_LOOPBACK", Esp32IrService::loopback);
  ok &= runtime.natives().add(IrisFunctions::IR_REPLAY, "IR_REPLAY",
                              irisIrReplay);
  ok &= runtime.natives().add(IrisFunctions::IR_REPLAY_LAST, "IR_REPLAY_LAST",
                              irisIrReplayLast);
  ok &= runtime.natives().add(IrisFunctions::IR_VERIFY_LAST, "IR_VERIFY_LAST",
                              irisIrVerifyLast);
  ok &= runtime.natives().add(IrisFunctions::IR_CAPTURE_INSPECT,
                              "IR_CAPTURE_INSPECT", irisIrCaptureInspect);
#endif
#if IRIS_ENABLE_SD
  ok &= runtime.natives().addText(IrisFunctions::VM_SAVE, "VM_SAVE", Esp32VmProgramStore::save);
  ok &= runtime.natives().addText(IrisFunctions::VM_LOAD_SAVED, "VM_LOAD_SAVED", Esp32VmProgramStore::load);
  ok &= runtime.natives().addText(IrisFunctions::VM_LIST_SAVED, "VM_LIST_SAVED", Esp32VmProgramStore::list);
  ok &= runtime.natives().addText(IrisFunctions::VM_DELETE_SAVED, "VM_DELETE_SAVED", Esp32VmProgramStore::remove);
  ok &= runtime.natives().add(IrisFunctions::VM_LAST_STATUS,
                              "VM_LAST_STATUS",
                              Esp32VmProgramStore::lastStatus);
  ok &= runtime.natives().add(IrisFunctions::VM_LAST_CLEAR,
                              "VM_LAST_CLEAR",
                              Esp32VmProgramStore::clearLast);
#endif
#if IRIS_ENABLE_BLE
  ok &= runtime.natives().add(IrisFunctions::BLE_SCAN, "BLE_SCAN", BleClientTransport::scan);
  ok &= runtime.natives().addText(IrisFunctions::BLE_PEER_SET, "BLE_PEER_SET", BleClientTransport::setPeer);
  ok &= runtime.natives().add(IrisFunctions::BLE_STATUS, "BLE_STATUS", BleClientTransport::nativeStatus);
#endif
#if IRIS_ENABLE_GPIO_DIAGNOSTICS
  ok &= runtime.natives().add(IrisFunctions::GPIO_AUDIT, "GPIO_AUDIT", Esp32GpioInspector::audit);
  ok &= runtime.natives().add(IrisFunctions::GPIO_INSPECT, "GPIO_INSPECT", Esp32GpioInspector::inspect);
  ok &= runtime.natives().add(IrisFunctions::GPIO_PULL_TEST, "GPIO_PULL_TEST", Esp32GpioInspector::pullTest);
#endif
#if IRIS_ENABLE_WIFI
  ok &= runtime.addService(Esp32WifiService::rssiService());
#endif
  ok &= runtime.addService(irisUltrasonicChangeThread());
  ok &= runtime.addService(irisLightChangeThread());
#if IRIS_ENABLE_MIC
  ok &= runtime.addService(irisMicRiseThread());
#endif
#if IRIS_ENABLE_WIFI && IRIS_ENABLE_SD
  ok &= runtime.addService(irisRssiThread());
#endif
#if IRIS_ENABLE_IR && IRIS_ENABLE_SD
  ok &= runtime.addService(irisIrThread());
#endif
#if IRIS_ENABLE_SD
  ok &= runtime.addService(irisEnvThread());
  const NativeResult restored = Esp32VmProgramStore::restoreLast();
  Serial.printf("NRP/1 0 EVENT VM_RESTORE ok=%d value=%ld detail=%s\n",
                restored.ok ? 1 : 0, long(restored.value),
                restored.detail.c_str());
#endif
  return ok;
}
