#ifndef NOOBIA_ARBITRATION_H
#define NOOBIA_ARBITRATION_H
#include "contact_book.h"
typedef struct { size_t next_index; char current_speaker[COUNCIL_NAME_LENGTH]; } arbitration_state;
void arbitration_init(arbitration_state *state);
const contact *arbitration_next(arbitration_state *state,
                                const contact_book *book,
                                const char *previous_speaker,
                                const int *online);
int arbitration_can_speak(const arbitration_state *state, const char *name);
void arbitration_grant(arbitration_state *state, const char *name);
#endif

