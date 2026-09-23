#include "Esp32AdcService.h"
#include <esp_adc/adc_oneshot.h>
#include <driver/gpio.h>
namespace {
int pins[8] = {-1,-1,-1,-1,-1,-1,-1,-1};
bool channelConfigured[8] = {};
adc_oneshot_unit_handle_t handles[2] = {nullptr, nullptr};
NativeResult error(const char *stage, esp_err_t code) {
  return {false, 0, String("ADC ")+stage+" error="+esp_err_to_name(code)};
}
int unitIndex(adc_unit_t unit) {
  if (unit == ADC_UNIT_1) return 0;
  if (unit == ADC_UNIT_2) return 1;
  return -1;
}
}
bool Esp32AdcService::configure(uint8_t channel, int pin) {
  adc_unit_t unit;
  adc_channel_t adcChannel;
  if (channel >= 8 || adc_oneshot_io_to_channel(pin, &unit, &adcChannel) != ESP_OK)
    return false;
  pins[channel] = pin;
  return true;
}
NativeResult Esp32AdcService::read(const int32_t *args, uint8_t count) {
  if (count < 1 || count > 2 || args[0] < 0 || args[0] >= 8 ||
      (count == 2 && (args[1] < 1 || args[1] > 64)))
    return {false, 0, "usage: channel(0..7) [samples(1..64)]"};
  int pin = pins[args[0]], samples = count == 2 ? args[1] : 16;
  if (pin < 0) return {false, 0, "ADC channel not registered"};
  adc_unit_t unit;
  adc_channel_t channel;
  esp_err_t err = adc_oneshot_io_to_channel(pin, &unit, &channel);
  if (err != ESP_OK) return error("mapping", err);
  const int index = unitIndex(unit);
  if (index < 0) return {false, 0, "ADC unit unsupported"};
  if (!handles[index]) {
    adc_oneshot_unit_init_cfg_t unitConfig = {};
    unitConfig.unit_id = unit;
    err = adc_oneshot_new_unit(&unitConfig, &handles[index]);
    if (err != ESP_OK) return error("open", err);
  }
  adc_oneshot_unit_handle_t handle = handles[index];
  if (!channelConfigured[args[0]]) {
    adc_oneshot_chan_cfg_t config = {};
    config.atten = ADC_ATTEN_DB_12;
    config.bitwidth = ADC_BITWIDTH_12;
    err = adc_oneshot_config_channel(handle, channel, &config);
    if (err == ESP_OK)
      err = gpio_set_pull_mode(gpio_num_t(pin), GPIO_FLOATING);
    if (err == ESP_OK) channelConfigured[args[0]] = true;
  }
  int total = 0, minimum = 4095, maximum = 0;
  for (int i = 0; err == ESP_OK && i < samples; ++i) {
    int value;
    err = adc_oneshot_read(handle, channel, &value);
    if (err != ESP_OK) break;
    total += value;
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
    if (i+1 < samples) delay(1);
  }
  if (err != ESP_OK) return error("sample", err);
  // Raw counts are relative voltage, not calibrated lux.
  int mean = (total+samples/2)/samples;
  return {true, mean, "pin="+String(pin)+" raw="+String(mean)+
      " min="+String(minimum)+" max="+String(maximum)+
      " samples="+String(samples)+" bits=12"};
}
