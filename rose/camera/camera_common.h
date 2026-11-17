#ifndef ROSE_CAMERA_COMMON_H
#define ROSE_CAMERA_COMMON_H

#include <stddef.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

const char *camera_setting(const char *name, const char *fallback);
int camera_temp_path(char *path, size_t size, const char *kind, const char *suffix);
int camera_run(char *const arguments[], unsigned int timeout_seconds);
int camera_file_ready(const char *path);

#endif
