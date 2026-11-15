#define _POSIX_C_SOURCE 200809L
#include "arbitration.h"
#include "contact_book.h"
#include "conversation_activity.h"
#include "conversation_summary.h"
#include "file_commands.h"
#include "network.h"
#include "presence.h"
#include "protocol.h"
#include "service_config.h"
#include "transcript.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#include <sys/socket.h>
#include <unistd.h>
#endif
#define CONVERSATION_LEASE_SECONDS 300
typedef struct {service_config config;contact_book contacts;arbitration_state arbitration;int online[COUNCIL_MAX_CONTACTS];time_t last_seen[COUNCIL_MAX_CONTACTS];time_t activity_until;unsigned long closure_id;int closure_active;int closure_expected[COUNCIL_MAX_CONTACTS];int closure_votes[COUNCIL_MAX_CONTACTS];char closure_proposer[COUNCIL_NAME_LENGTH];volatile int stopping;} council_service;
typedef struct {council_service*service;network_socket socket;contact_role listener_role;} connection;
typedef struct {council_service*service;contact_role role;} listener_args;
static council_service service;
#ifdef _WIN32
static CRITICAL_SECTION state_lock;
#define LOCK() EnterCriticalSection(&state_lock)
#define UNLOCK() LeaveCriticalSection(&state_lock)
#else
static pthread_mutex_t state_lock=PTHREAD_MUTEX_INITIALIZER;
#define LOCK() pthread_mutex_lock(&state_lock)
#define UNLOCK() pthread_mutex_unlock(&state_lock)
#endif
static size_t contact_index(council_service*s,const contact*p){return(size_t)(p-s->contacts.items);}
static void mark_seen(council_service*s,const contact*p){size_t i=contact_index(s,p);LOCK();s->online[i]=1;s->last_seen[i]=time(NULL);UNLOCK();}
static const char*activity_log(council_service*s){return s->config.is_hub?s->config.transcript_path:s->config.inbox_path;}
static void mark_activity(council_service*s){LOCK();s->activity_until=time(NULL)+CONVERSATION_LEASE_SECONDS;UNLOCK();conversation_activity_mark(s->config.activity_path);}
static int busy_remaining(council_service*s){int remaining=conversation_activity_remaining(s->config.activity_path,activity_log(s),CONVERSATION_LEASE_SECONDS);time_t now=time(NULL);LOCK();if(s->activity_until>now&&s->activity_until-now>remaining)remaining=(int)(s->activity_until-now);UNLOCK();return remaining;}
static int reserve_initiation(council_service*s){int remaining;time_t now=time(NULL);LOCK();remaining=conversation_activity_remaining(s->config.activity_path,activity_log(s),CONVERSATION_LEASE_SECONDS);if(s->activity_until>now&&s->activity_until-now>remaining)remaining=(int)(s->activity_until-now);if(!remaining){s->activity_until=now+CONVERSATION_LEASE_SECONDS;conversation_activity_mark(s->config.activity_path);}UNLOCK();return remaining;}
static void release_initiation(council_service*s){LOCK();s->activity_until=0;conversation_activity_clear(s->config.activity_path);UNLOCK();}
static int outbound_contact(council_service*s,const contact*to,contact*out){const contact*self=contact_book_find(&s->contacts,s->config.name);if(!self)return-1;*out=*to;snprintf(out->shared_key,sizeof(out->shared_key),"%s",self->shared_key);return 0;}
static int deliver(council_service*s,const contact*to,const char*command){contact authenticated;char reply[128];int ok=!outbound_contact(s,to,&authenticated)&&!protocol_send_command(&authenticated,s->config.name,command,reply,sizeof(reply));LOCK();s->online[contact_index(s,to)]=ok;UNLOCK();return ok?0:-1;}
static const contact *message_target(council_service *s, const char *message,
                                     int *addressed) {
    const char *delimiter = strpbrk(message, ",:");
    size_t i, prefix_length;
    *addressed = 0;
    if (!delimiter || memchr(message, ' ', (size_t)(delimiter-message))) return NULL;
    prefix_length = (size_t)(delimiter-message);
    for (i=0; i<s->contacts.count; i++) {
        const contact *candidate = &s->contacts.items[i];
        if (strlen(candidate->name)==prefix_length &&
            !strncmp(message,candidate->name,prefix_length)) {
            *addressed = 1;
            return candidate;
        }
    }
    return NULL;
}
static int relay_message(council_service *s, const contact *from,
                         const char *message) {
    size_t i;
    char command[COUNCIL_MESSAGE_LENGTH];
    const contact *next = NULL;
    int addressed, limit=(int)(sizeof(command)-strlen(from->name)-10);
    const contact *target=message_target(s,message,&addressed);
    if (addressed && !target) return -2;
    if (target==from) return -3;
    if(target&&target->role==CONTACT_HUMAN){
        LOCK();
        if(s->online[contact_index(s,target)])next=target;
        UNLOCK();
    }
    for (i=0; i<s->contacts.count; i++) {
        const contact *destination=&s->contacts.items[i];
        if (destination->role!=CONTACT_AI || destination==from ||
            (target && destination!=target)) continue;
        snprintf(command,sizeof(command),"DELIVER %s %.*s",
                 from->name,limit,message);
        if (!deliver(s,destination,command) && target) next=target;
    }
    if (!target) {
        LOCK();
        next=arbitration_next(&s->arbitration,&s->contacts,
                              from->name,s->online);
        UNLOCK();
    } else if (next) {
        LOCK(); arbitration_grant(&s->arbitration,next->name); UNLOCK();
    }
    if (!next) return -1;
    if(next->role==CONTACT_AI){
        snprintf(command,sizeof(command),"SPEAK %s",from->name);
        deliver(s,next,command);
    }
    transcript_append(s->config.transcript_path,s->config.name,
                      "grant",next->name);
    return 0;
}
static void send_status(council_service*s,network_socket socket){
    size_t i;char line[256],current[COUNCIL_NAME_LENGTH],command[128];
    time_t now=time(NULL);const contact*holder=NULL,*next;
    for(i=0;i<s->contacts.count;i++){
        const contact*p=&s->contacts.items[i];int online;
        if(p->role==CONTACT_AI){contact authenticated;online=!outbound_contact(s,p,&authenticated)&&presence_check(&authenticated,s->config.name);}
        else online=s->last_seen[i]&&now-s->last_seen[i]<=s->config.presence_seconds;
        LOCK();s->online[i]=online;UNLOCK();
        snprintf(line,sizeof(line),"PRESENCE %s %s\n",p->name,online?"online":"offline");
        network_send(socket,line);
    }
    network_send(socket,"END\n");
    LOCK();snprintf(current,sizeof(current),"%s",s->arbitration.current_speaker);UNLOCK();
    if(!current[0])return;
    for(i=0;i<s->contacts.count;i++){
        if(!strcmp(s->contacts.items[i].name,current)){
            holder=&s->contacts.items[i];
            break;
        }
    }
    if(holder&&s->online[contact_index(s,holder)])return;
    LOCK();
    next=arbitration_next(&s->arbitration,&s->contacts,current,s->online);
    UNLOCK();
    if(next){
        if(next->role==CONTACT_AI){
            snprintf(command,sizeof(command),"SPEAK offline:%s",current);
            deliver(s,next,command);
        }
        snprintf(line,sizeof(line),"%s -> %s",current,next->name);
        transcript_append(s->config.transcript_path,s->config.name,"offline-grant",line);
    }
}
static void send_events(council_service*s,network_socket socket,long offset){char line[256],speaker[COUNCIL_NAME_LENGTH],proposer[COUNCIL_NAME_LENGTH];long next=0;unsigned long closure_id;int closure_active;if(!s->config.is_hub){network_send(socket,"ERROR NOT_ARBITER\n");return;}if(transcript_stream_since(s->config.transcript_path,offset,socket,&next)){network_send(socket,"ERROR TRANSCRIPT\n");return;}LOCK();snprintf(speaker,sizeof(speaker),"%s",s->arbitration.current_speaker);closure_active=s->closure_active;closure_id=s->closure_id;snprintf(proposer,sizeof(proposer),"%s",s->closure_proposer);UNLOCK();snprintf(line,sizeof(line),"CURSOR %ld\n",next);network_send(socket,line);snprintf(line,sizeof(line),"TURN %s\n",speaker[0]?speaker:"none");network_send(socket,line);snprintf(line,sizeof(line),"CLOSURE %s %lu %s\n",closure_active?"open":"none",closure_id,closure_active?proposer:"none");network_send(socket,line);network_send(socket,"END\n");}
static void send_context(council_service*s,network_socket socket,const contact*person){if(!s->config.is_hub){network_send(socket,"ERROR NOT_ARBITER\n");return;}network_send(socket,"CONTEXT_BEGIN\n");if(transcript_stream_context(s->config.transcript_path,person->name,socket)){network_send(socket,"ERROR TRANSCRIPT\n");return;}network_send(socket,"CONTEXT_END\n");}
static int closure_complete(council_service*s){size_t i;for(i=0;i<s->contacts.count;i++)if(s->closure_expected[i]&&s->closure_votes[i]!=1)return 0;return 1;}
static void closure_finish(council_service*s){char detail[128];snprintf(detail,sizeof(detail),"proposal=%lu unanimous",s->closure_id);transcript_append(s->config.transcript_path,s->config.name,"conversation-end",detail);LOCK();s->closure_active=0;arbitration_grant(&s->arbitration,"");UNLOCK();release_initiation(s);}
static void closure_propose(council_service*s,network_socket socket,const contact*person,const char*reason,int has_turn){size_t i,proposer_index=contact_index(s,person);time_t now=time(NULL);char detail[COUNCIL_MESSAGE_LENGTH];if(!s->config.is_hub||person->arbiter_priority<=0){network_send(socket,"ERROR ARBITER_ONLY\n");return;}if(!has_turn){network_send(socket,"ERROR NOT_YOUR_TURN\n");return;}LOCK();if(s->closure_active){UNLOCK();network_send(socket,"ERROR CLOSURE_ACTIVE\n");return;}s->closure_active=1;s->closure_id=(unsigned long)now;snprintf(s->closure_proposer,sizeof(s->closure_proposer),"%s",person->name);memset(s->closure_expected,0,sizeof(s->closure_expected));memset(s->closure_votes,0,sizeof(s->closure_votes));for(i=0;i<s->contacts.count;i++){int online=s->contacts.items[i].role==CONTACT_AI?s->online[i]:(s->last_seen[i]&&now-s->last_seen[i]<=s->config.presence_seconds);if(online){s->closure_expected[i]=1;s->closure_votes[i]=i==proposer_index?1:0;}}UNLOCK();snprintf(detail,sizeof(detail),"proposal=%lu reason=%.*s",s->closure_id,(int)sizeof(detail)-48,reason&&reason[0]?reason:"conversation appears complete");transcript_append(s->config.transcript_path,person->name,"end-proposal",detail);network_send(socket,"ACCEPTED\n");if(closure_complete(s))closure_finish(s);}
static void closure_vote(council_service*s,network_socket socket,const contact*person,const char*vote){size_t i=contact_index(s,person);char detail[COUNCIL_MESSAGE_LENGTH];const char*reason;int close_vote=!strncmp(vote,"close",5)&&(vote[5]==0||vote[5]==' '),continue_vote=!strncmp(vote,"continue ",9)&&vote[9];if(!close_vote&&!continue_vote){network_send(socket,"ERROR VOTE_USE_CLOSE_OR_CONTINUE_WITH_REASON\n");return;}reason=strchr(vote,' ');reason=reason?reason+1:(close_vote?"no further matters":"");LOCK();if(!s->closure_active||!s->closure_expected[i]){UNLOCK();network_send(socket,"ERROR NO_CLOSURE_VOTE\n");return;}s->closure_votes[i]=close_vote?1:-1;snprintf(detail,sizeof(detail),"proposal=%lu vote=%s reason=%.*s",s->closure_id,close_vote?"close":"continue",(int)sizeof(detail)-80,reason);UNLOCK();transcript_append(s->config.transcript_path,person->name,"end-vote",detail);network_send(socket,"ACCEPTED\n");if(continue_vote){LOCK();s->closure_active=0;arbitration_grant(&s->arbitration,person->name);UNLOCK();transcript_append(s->config.transcript_path,s->config.name,"end-cancelled",person->name);transcript_append(s->config.transcript_path,s->config.name,"grant",person->name);mark_activity(s);}else if(closure_complete(s))closure_finish(s);}
static void accept_message(council_service*s,network_socket socket,const contact*person,const char*message,const char*event,int reserved){
    int routed=relay_message(s,person,message);
    if(routed==-2){if(reserved)release_initiation(s);network_send(socket,"ERROR TARGET_UNKNOWN\n");return;}
    if(routed==-3){if(reserved)release_initiation(s);network_send(socket,"ERROR TARGET_SELF\n");return;}
    if(routed){if(reserved)release_initiation(s);network_send(socket,"ERROR TARGET_OFFLINE\n");return;}
    transcript_append(s->config.transcript_path,person->name,event,message);
    mark_activity(s);
    network_send(socket,"ACCEPTED\n");
}
static void handle_connection(connection*c){
    char line[COUNCIL_MESSAGE_LENGTH],reply[64];
    const contact*person=NULL;
    council_service*s=c->service;
    int has_turn;
    if(protocol_accept_identity(c->socket,&s->contacts,c->listener_role,&person))goto done;
    mark_seen(s,person);
    if(network_read_line(c->socket,line,sizeof(line))<0)goto done;
    LOCK();
    has_turn=arbitration_can_speak(&s->arbitration,person->name);
    UNLOCK();
    if(file_command_handle(line,c->socket,person,&s->config,&s->contacts,has_turn))goto done;
    if(!strcmp(line,"PING"))network_send(c->socket,"PONG\n");
    else if(!strcmp(line,"BUSY")){
        int remaining=busy_remaining(s);
        if(remaining)snprintf(reply,sizeof(reply),"BUSY %d\n",remaining);
        else snprintf(reply,sizeof(reply),"IDLE\n");
        network_send(c->socket,reply);
    }
    else if(!strcmp(line,"STATUS"))send_status(s,c->socket);
    else if(!strncmp(line,"EVENTS ",7))send_events(s,c->socket,strtol(line+7,NULL,10));
    else if(!strcmp(line,"CONTEXT"))send_context(s,c->socket,person);
    else if(!strncmp(line,"END_PROPOSE ",12))closure_propose(s,c->socket,person,line+12,has_turn);
    else if(!strncmp(line,"END_VOTE ",9))closure_vote(s,c->socket,person,line+9);
    else if(!strncmp(line,"INITIATE ",9)){
        int remaining=reserve_initiation(s);
        if(remaining){snprintf(reply,sizeof(reply),"BUSY %d\n",remaining);network_send(c->socket,reply);}
        else accept_message(s,c->socket,person,line+9,"initiate",1);
    }
    else if(!strncmp(line,"SAY ",4)){
        if(!has_turn)network_send(c->socket,"ERROR NOT_YOUR_TURN\n");
        else accept_message(s,c->socket,person,line+4,"message",0);
    }
    else if(!strncmp(line,"DELIVER ",8)){
        transcript_append(s->config.inbox_path,person->name,"message",line+8);
        mark_activity(s);network_send(c->socket,"ACCEPTED\n");
    }
    else if(!strncmp(line,"SPEAK ",6)){
        transcript_append(s->config.inbox_path,person->name,"speak",line+6);
        network_send(c->socket,"ACCEPTED\n");
    }
    else if(!strncmp(line,"GRANT ",6)&&s->config.is_hub){
        LOCK();arbitration_grant(&s->arbitration,line+6);UNLOCK();
        transcript_append(s->config.transcript_path,person->name,"grant",line+6);
        network_send(c->socket,"ACCEPTED\n");
    }
    else network_send(c->socket,"ERROR COMMAND\n");
done:
    network_close(c->socket);
    free(c);
}
#ifdef _WIN32
static DWORD WINAPI connection_thread(LPVOID v){handle_connection(v);return 0;}
static DWORD WINAPI listener_thread(LPVOID v)
#else
static void*connection_thread(void*v){handle_connection(v);return NULL;}
static void*listener_thread(void*v)
#endif
{listener_args*a=v;council_service*s=a->service;uint16_t port=a->role==CONTACT_HUMAN?s->config.human_port:s->config.ai_port;network_socket listener=network_listen(s->config.bind_address,port);if(listener==INVALID_NETWORK_SOCKET){fprintf(stderr,"cannot listen on %u\n",port);s->stopping=1;free(a);return 0;}while(!s->stopping){connection*c=malloc(sizeof(*c));if(!c)break;c->service=s;c->listener_role=a->role;c->socket=accept(listener,NULL,NULL);if(c->socket==INVALID_NETWORK_SOCKET){free(c);continue;}
#ifdef _WIN32
CloseHandle(CreateThread(NULL,0,connection_thread,c,0,NULL));
#else
{pthread_t thread;if(!pthread_create(&thread,NULL,connection_thread,c))pthread_detach(thread);else free(c);}
#endif
}network_close(listener);free(a);return 0;}
static void stop_service(int n){(void)n;service.stopping=1;}
static int start_listener(contact_role role){listener_args*a=malloc(sizeof(*a));if(!a)return-1;a->service=&service;a->role=role;
#ifdef _WIN32
{HANDLE t=CreateThread(NULL,0,listener_thread,a,0,NULL);if(!t){free(a);return-1;}CloseHandle(t);}
#else
{pthread_t t;if(pthread_create(&t,NULL,listener_thread,a)){free(a);return-1;}pthread_detach(t);}
#endif
return 0;}
int main(int argc,char**argv){char error[256],restored_speaker[COUNCIL_NAME_LENGTH];const char*log_path;if(argc!=3||strcmp(argv[1],"--config")){fputs("usage: noobia-council --config FILE\n",stderr);return 2;}if(service_config_load(argv[2],&service.config,error,sizeof(error))||contact_book_load(service.config.contacts_path,&service.contacts,error,sizeof(error))){fprintf(stderr,"configuration: %s\n",error);return 2;}log_path=service.config.is_hub?service.config.transcript_path:service.config.inbox_path;if(conversation_summary_rebuild(log_path,service.config.summary_path))fprintf(stderr,"warning: could not rebuild conversation summary\n");if(network_start()){fputs("network startup failed\n",stderr);return 1;}arbitration_init(&service.arbitration);if(service.config.is_hub&&!transcript_last_speaker(service.config.transcript_path,restored_speaker,sizeof(restored_speaker))){if(restored_speaker[0])arbitration_grant(&service.arbitration,restored_speaker);else conversation_activity_clear(service.config.activity_path);}
#ifdef _WIN32
InitializeCriticalSection(&state_lock);
#endif
signal(SIGINT,stop_service);signal(SIGTERM,stop_service);if(start_listener(CONTACT_HUMAN)||start_listener(CONTACT_AI))return 1;fprintf(stderr,"%s listening on human %u and AI %u\n",service.config.name,service.config.human_port,service.config.ai_port);while(!service.stopping){
#ifdef _WIN32
Sleep(250);
#else
struct timespec delay={0,250000000};nanosleep(&delay,NULL);
#endif
}network_stop();return 0;}
