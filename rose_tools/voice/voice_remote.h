#ifndef ROSE_VOICE_REMOTE_H
#define ROSE_VOICE_REMOTE_H

#include "contact_book.h"

typedef enum {
    VOICE_TASK_PIPER,
    VOICE_TASK_SOX,
    VOICE_TASK_ENVELOPE
} voice_task;

int voice_remote_available(const contact *worker, const contact *sender);
int voice_remote_run(const contact *worker, const contact *sender, voice_task task,
                     const char *input_path, const char *output_path);

#endif
