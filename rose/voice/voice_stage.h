#ifndef ROSE_VOICE_STAGE_H
#define ROSE_VOICE_STAGE_H

#include <stddef.h>

int voice_stage_piper(const char *text_path, const char *output_path);
int voice_stage_sox(const char *input_path, const char *output_path);
int voice_stage_envelope(const char *input_path, const char *output_path);
int voice_envelope_load(const char *path, unsigned char **levels, size_t *count,
                        double *hop_seconds);

#endif
