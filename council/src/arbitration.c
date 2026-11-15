#include "arbitration.h"
#include <stdio.h>
#include <string.h>
void arbitration_init(arbitration_state*s){memset(s,0,sizeof(*s));}
const contact*arbitration_next(arbitration_state*s,const contact_book*b,const char*previous,const int*online){size_t checked;for(checked=0;checked<b->count;checked++){size_t i=(s->next_index+checked)%b->count;const contact*c=&b->items[i];if(online[i]&&strcmp(c->name,previous)){s->next_index=(i+1)%b->count;arbitration_grant(s,c->name);return c;}}s->current_speaker[0]=0;return NULL;}
int arbitration_can_speak(const arbitration_state*s,const char*n){return !s->current_speaker[0]||!strcmp(s->current_speaker,n);}
void arbitration_grant(arbitration_state*s,const char*n){snprintf(s->current_speaker,sizeof(s->current_speaker),"%s",n);}
