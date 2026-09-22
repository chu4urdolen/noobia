#pragma once

// Override any value with a compiler -D option.
#ifndef DIAG_SDA_PIN
#define DIAG_SDA_PIN 15
#endif
#ifndef DIAG_SCL_PIN
#define DIAG_SCL_PIN 16
#endif
#ifndef DIAG_SIGNAL_LED_PIN
#define DIAG_SIGNAL_LED_PIN 34
#endif
#ifndef DIAG_I2C_HZ
#define DIAG_I2C_HZ 100000
#endif
#ifndef DIAG_OLED_ADDRESS
#define DIAG_OLED_ADDRESS 0x3c
#endif
#ifndef DIAG_RETRY_COUNT
#define DIAG_RETRY_COUNT 100
#endif
#ifndef DIAG_WRITE_PAUSE_MS
#define DIAG_WRITE_PAUSE_MS 20
#endif
