#define _POSIX_C_SOURCE 200809L
#include "contact_book.h"
#include "network.h"
#include "protocol.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <conio.h>
#include <windows.h>
#else
#include <sys/select.h>
#include <unistd.h>
#endif
static void usage(void){fputs("usage: council-live --host H --port P --name N --key-file F\n",stderr);}
static int read_key(const char*path,char*out,size_t size){FILE*f=fopen(path,"r");if(!f)return-1;if(!fgets(out,(int)size,f)){fclose(f);return-1;}fclose(f);out[strcspn(out,"\r\n")]=0;return out[0]?0:-1;}
static void show_record(const char*prefix,const char*line){char copy[8192],*stamp,*speaker,*event,*message;snprintf(copy,sizeof(copy),"%s",line+strlen(prefix));stamp=strtok(copy,"\t");speaker=strtok(NULL,"\t");event=strtok(NULL,"\t");message=strtok(NULL,"");if(stamp&&speaker&&event&&message)printf("[%s] %s (%s): %s\n",stamp,speaker,event,message);else printf("%s\n",line+strlen(prefix));}
static int request(contact*hub,const char*name,const char*command,long*cursor,char*turn,size_t turn_size,int context){network_socket socket;char line[8224];if(protocol_connect_identity(hub,name,&socket))return-1;if(network_send(socket,command)){network_close(socket);return-1;}while(network_read_line(socket,line,sizeof(line))>=0){if(!strncmp(line,"EVENT ",6))show_record("EVENT ",line);else if(!strncmp(line,"CONTEXT ",8))show_record("CONTEXT ",line);else if(!strncmp(line,"CURSOR ",7))*cursor=strtol(line+7,NULL,10);else if(!strncmp(line,"TURN ",5)){strncpy(turn,line+5,turn_size-1);turn[turn_size-1]=0;}else if(!strncmp(line,"CLOSURE open ",13))printf("\n--- CLOSURE PROPOSED by %s — use /end close REASON or /end continue WHAT_REMAINS ---\n",strrchr(line,' ')?strrchr(line,' ')+1:"arbiter");else if(!strcmp(line,context?"CONTEXT_END":"END"))break;else if(!strncmp(line,"ERROR",5)){fprintf(stderr,"%s\n",line);network_close(socket);return-1;}}network_close(socket);return 0;}
static int say(contact*hub,const char*name,const char*message){network_socket socket;char command[8192],reply[256];size_t length=strlen(message);if(length>sizeof(command)-6||strchr(message,'\n')||strchr(message,'\r')||protocol_connect_identity(hub,name,&socket))return-1;snprintf(command,sizeof(command),"SAY %s\n",message);if(network_send(socket,command)||network_read_line(socket,reply,sizeof(reply))<0){network_close(socket);return-1;}network_close(socket);if(strcmp(reply,"ACCEPTED")){fprintf(stderr,"%s\n",reply);return-1;}return 0;}
static int end_vote(contact*hub,const char*name,const char*vote){network_socket socket;char command[8192],reply[256];size_t length=strlen(vote);if((strncmp(vote,"close",5)||!(vote[5]==0||vote[5]==' '))&&(strncmp(vote,"continue ",9)||!vote[9]))return-1;if(length>sizeof(command)-11||protocol_connect_identity(hub,name,&socket))return-1;snprintf(command,sizeof(command),"END_VOTE %s\n",vote);if(network_send(socket,command)||network_read_line(socket,reply,sizeof(reply))<0){network_close(socket);return-1;}network_close(socket);if(strcmp(reply,"ACCEPTED")){fprintf(stderr,"%s\n",reply);return-1;}puts("[closure response accepted]");return 0;}
static int input_ready(void){
#ifdef _WIN32
Sleep(200);return _kbhit();
#else
fd_set set;struct timeval timeout;FD_ZERO(&set);FD_SET(STDIN_FILENO,&set);timeout.tv_sec=0;timeout.tv_usec=200000;return select(STDIN_FILENO+1,&set,NULL,NULL,&timeout)>0;
#endif
}
int main(int argc,char**argv){contact hub;const char*name=NULL,*key=NULL;char line[8192],command[128],turn[64]="none",last_turn[64]="";long cursor=0;int i,shown_prompt=0;memset(&hub,0,sizeof(hub));for(i=1;i<argc;i++){if(!strcmp(argv[i],"--host")&&++i<argc)snprintf(hub.host,sizeof(hub.host),"%s",argv[i]);else if(!strcmp(argv[i],"--port")&&++i<argc)hub.port=(uint16_t)atoi(argv[i]);else if(!strcmp(argv[i],"--name")&&++i<argc)name=argv[i];else if(!strcmp(argv[i],"--key-file")&&++i<argc)key=argv[i];else{usage();return 2;}}if(!hub.host[0]||!hub.port||!name||!key||read_key(key,hub.shared_key,sizeof(hub.shared_key))){usage();return 2;}if(network_start())return 1;printf("Noobia Council live view — %s\nType /context, /end close REASON, /end continue WHAT_REMAINS, /quit, or a turn message.\n",name);for(;;){snprintf(command,sizeof(command),"EVENTS %ld\n",cursor);if(request(&hub,name,command,&cursor,turn,sizeof(turn),0)){fputs("Council unavailable; reconnecting...\n",stderr);shown_prompt=0;}if(strcmp(turn,last_turn)){printf("--- TURN: %s%s ---\n",turn,!strcmp(turn,name)?" (you)":"");if(!strcmp(turn,name)){long ignored=0;puts("--- Conversation since your previous turn ---");request(&hub,name,"CONTEXT\n",&ignored,turn,sizeof(turn),1);puts("--- You may speak ---");}memcpy(last_turn,turn,sizeof(last_turn));shown_prompt=0;}if(!shown_prompt){fputs(!strcmp(turn,name)?"> ":"[watching] ",stdout);fflush(stdout);shown_prompt=1;}if(!input_ready())continue;if(!fgets(line,sizeof(line),stdin))break;shown_prompt=0;line[strcspn(line,"\r\n")]=0;if(!strcmp(line,"/quit"))break;if(!strcmp(line,"/context")){long ignored=0;request(&hub,name,"CONTEXT\n",&ignored,turn,sizeof(turn),1);continue;}if(!strncmp(line,"/end ",5)){if(end_vote(&hub,name,line+5))fputs("Use /end close REASON or /end continue WHAT_REMAINS.\n",stderr);continue;}if(!line[0])continue;if(strcmp(turn,name)){fprintf(stderr,"It is %s's turn; your message was not sent.\n",turn);continue;}if(!say(&hub,name,line))puts("[sent]");}network_stop();return 0;}
