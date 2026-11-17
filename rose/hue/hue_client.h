#ifndef ROSE_HUE_CLIENT_H
#define ROSE_HUE_CLIENT_H

#include <stdbool.h>
#include <stddef.h>

struct hue_config {
    char bridge[256];
    char username[256];
    char target[64];
};

int hue_config_load(struct hue_config *config);
int hue_set_rgb(const struct hue_config *config, unsigned int red, unsigned int green,
                unsigned int blue, unsigned int brightness, double transition_seconds,
                char *error, size_t error_size);
int hue_lock_acquire(unsigned int timeout_seconds, char *error, size_t error_size);
void hue_lock_release(void);
void hue_lock_force_clear(void);
int hue_dark(const struct hue_config *config, char *error, size_t error_size);

#endif
