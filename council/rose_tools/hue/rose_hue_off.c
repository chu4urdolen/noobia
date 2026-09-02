#include "hue_client.h"

#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    struct hue_config config;
    char error[256];
    hue_lock_force_clear();
    if (hue_config_load(&config) != 0) {
        fprintf(stderr, "Hue is not configured\n");
        return EXIT_FAILURE;
    }
    if (hue_dark(&config, error, sizeof(error)) != 0) {
        fprintf(stderr, "%s\n", error);
        return EXIT_FAILURE;
    }
    hue_lock_force_clear();
    return EXIT_SUCCESS;
}
