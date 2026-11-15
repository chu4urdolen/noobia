#pragma once
#include "noob_native_registry.h"

typedef void (*NoobReply)(int, unsigned, const char *, const char *);
void hw_display_bind(NoobReply reply);
void hw_display_call(int client, unsigned id, const char *name,
                      const NoobNativeArguments *args);
