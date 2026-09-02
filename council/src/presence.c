#include "presence.h"
#include "protocol.h"
#include <string.h>
int presence_check(const contact*p,const char*local_name){char reply[64];return !protocol_send_command(p,local_name,"PING",reply,sizeof(reply))&&!strcmp(reply,"PONG");}
