#pragma once
#include "hw_display.h"
void hw_led_bind(NoobReply reply);
int hw_led_boot(void);
void hw_led_call(int client, unsigned id, const char *name,
                 const NoobNativeArguments *args);
