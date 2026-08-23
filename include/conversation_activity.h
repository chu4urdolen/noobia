#ifndef NOOBIA_CONVERSATION_ACTIVITY_H
#define NOOBIA_CONVERSATION_ACTIVITY_H
int conversation_activity_mark(const char *state_path);
int conversation_activity_clear(const char *state_path);
int conversation_activity_remaining(const char *state_path,
                                    const char *fallback_log_path,
                                    int lease_seconds);
#endif
