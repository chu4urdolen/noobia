#pragma once
#define NOOB_LED_CHIP "/dev/gpiochip0"
#define NOOB_LED_BOOT_PIN 23
/* Iris Neo physical header pins, not ESP GPIO numbers. */
static const struct { int pin; unsigned line; } noob_led_pins[] = {
  {7, 203}, {11, 0}, {12, 6}, {13, 2}, {15, 3},
  {19, 64}, {21, 65}, {22, 1}, {23, 66}, {24, 67}
};
