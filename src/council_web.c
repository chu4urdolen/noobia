#define _POSIX_C_SOURCE 200809L
#include "contact_book.h"
#include "network.h"
#include "protocol.h"
#include "web_page.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/socket.h>
#endif

#define REQUEST_CAPACITY 16384
#define COUNCIL_REPLY_CAPACITY (2U*1024U*1024U)

typedef struct {
    contact hub;
    char name[COUNCIL_NAME_LENGTH];
    char authorization[1024];
} web_config;

static int read_secret(const char*path,char*out,size_t size){
    FILE*f=fopen(path,"r");
    if(!f)return-1;
    if(!fgets(out,(int)size,f)){fclose(f);return-1;}
    fclose(f);
    out[strcspn(out,"\r\n")]=0;
    return out[0]?0:-1;
}

static int base64(const unsigned char*in,size_t length,char*out,size_t size){
    static const char table[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i,used=0;
    for(i=0;i<length;i+=3){
        unsigned value=(unsigned)in[i]<<16;
        int remaining=(int)(length-i);
        if(remaining>1)value|=(unsigned)in[i+1]<<8;
        if(remaining>2)value|=in[i+2];
        if(used+4>=size)return-1;
        out[used++]=table[(value>>18)&63];out[used++]=table[(value>>12)&63];
        out[used++]=remaining>1?table[(value>>6)&63]:'=';
        out[used++]=remaining>2?table[value&63]:'=';
    }
    out[used]=0;
    return 0;
}

static int make_authorization(const char*name,const char*password,char*out,size_t size){
    char plain[512],encoded[768];
    if(snprintf(plain,sizeof(plain),"%s:%s",name,password)>=(int)sizeof(plain)||
       base64((const unsigned char*)plain,strlen(plain),encoded,sizeof(encoded)))return-1;
    return snprintf(out,size,"Basic %s",encoded)>=(int)size?-1:0;
}

static int authorized(const char*request,const char*wanted){
    const char*line=strstr(request,"\r\nAuthorization: ");
    size_t length;
    if(!line)return 0;
    line+=17;
    length=strcspn(line,"\r\n");
    return strlen(wanted)==length&&!memcmp(line,wanted,length);
}

static void http_reply(network_socket socket,int code,const char*type,
                       const char*body,size_t length){
    char header[512];
    const char*reason=code==200?"OK":code==401?"Unauthorized":
                      code==409?"Conflict":"Bad Request";
    int count=snprintf(header,sizeof(header),
        "HTTP/1.1 %d %s\r\nContent-Type: %s; charset=utf-8\r\n"
        "Content-Length: %zu\r\nCache-Control: no-store\r\n"
        "Connection: close\r\n%s\r\n",code,reason,type,length,
        code==401?"WWW-Authenticate: Basic realm=\"Noobia Council\"\r\n":"");
    network_send_bytes(socket,header,(size_t)count);
    network_send_bytes(socket,body,length);
}

static void http_page_reply(network_socket socket){
    char header[384];
    size_t length=council_web_page_layout_size+council_web_page_controller_size;
    int count=snprintf(header,sizeof(header),
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
        "Content-Length: %zu\r\nCache-Control: no-store\r\n"
        "Connection: close\r\n\r\n",length);
    network_send_bytes(socket,header,(size_t)count);
    network_send_bytes(socket,council_web_page_layout,council_web_page_layout_size);
    network_send_bytes(socket,council_web_page_controller,council_web_page_controller_size);
}

static int council_exchange(const web_config*config,const char*command,
                            int multiline,char*out,size_t size){
    network_socket socket;
    char wire[8192],line[8224];
    size_t used=0;
    if(strchr(command,'\r')||strchr(command,'\n')||
       snprintf(wire,sizeof(wire),"%s\n",command)>=(int)sizeof(wire)||
       protocol_connect_identity(&config->hub,config->name,&socket))return-1;
    if(network_send(socket,wire)){network_close(socket);return-1;}
    while(network_read_line(socket,line,sizeof(line))>=0){
        size_t length=strlen(line);
        if(length+used+2>size){network_close(socket);return-1;}
        memcpy(out+used,line,length);used+=length;out[used++]='\n';out[used]=0;
        if(!multiline||!strcmp(line,"END"))break;
    }
    network_close(socket);
    return used?0:-1;
}

static int receive_request(network_socket socket,char*request,size_t size,
                           char**body){
    size_t used=0,needed=0;
    char*headers;
    while(used+1<size){
        int count=recv(socket,request+used,(int)(size-used-1),0);
        char*length_header;
        if(count<=0)return-1;
        used+=(size_t)count;request[used]=0;
        headers=strstr(request,"\r\n\r\n");
        if(!headers)continue;
        *body=headers+4;
        length_header=strstr(request,"\r\nContent-Length:");
        if(length_header)needed=(size_t)strtoul(length_header+17,NULL,10);
        if(used>=(size_t)(*body-request)+needed)return 0;
    }
    return-1;
}

static int clean_message(char*message){
    size_t length=strlen(message);
    while(length&&(message[length-1]=='\r'||message[length-1]=='\n'||
                   isspace((unsigned char)message[length-1])))message[--length]=0;
    while(*message&&isspace((unsigned char)*message))memmove(message,message+1,strlen(message));
    return !message[0]||strchr(message,'\r')||strchr(message,'\n')||length>7900?-1:0;
}

static void handle_request(network_socket client,const web_config*config){
    char request[REQUEST_CAPACITY],method[8],path[512],*body,*reply,*command;
    int multiline=0,code=200;
    if(receive_request(client,request,sizeof(request),&body)||
       sscanf(request,"%7s %511s",method,path)!=2){
        http_reply(client,400,"text/plain","bad request\n",12);return;
    }
    if(!authorized(request,config->authorization)){
        http_reply(client,401,"text/plain","authentication required\n",24);return;
    }
    if(!strcmp(method,"GET")&&!strcmp(path,"/")){
        http_page_reply(client);return;
    }
    reply=malloc(COUNCIL_REPLY_CAPACITY);
    if(!reply){http_reply(client,400,"text/plain","out of memory\n",14);return;}
    reply[0]=0;
    if(!strcmp(method,"GET")&&!strncmp(path,"/api/events?cursor=",19)){
        unsigned long cursor=strtoul(path+19,NULL,10);
        command=malloc(64);
        if(command)snprintf(command,64,"EVENTS %lu",cursor);
        multiline=1;
    }else if(!strcmp(method,"GET")&&!strcmp(path,"/api/status")){
        command=strdup("STATUS");multiline=1;
    }else if(!strcmp(method,"POST")&&
             (!strcmp(path,"/api/initiate")||!strcmp(path,"/api/say")||
              !strcmp(path,"/api/vote"))){
        const char*verb=!strcmp(path,"/api/initiate")?"INITIATE":
                        !strcmp(path,"/api/say")?"SAY":"END_VOTE";
        if(clean_message(body)){free(reply);http_reply(client,400,"text/plain","invalid message\n",16);return;}
        command=malloc(strlen(verb)+strlen(body)+2);
        if(command)sprintf(command,"%s %s",verb,body);
    }else{
        free(reply);http_reply(client,400,"text/plain","unknown endpoint\n",17);return;
    }
    if(!command||council_exchange(config,command,multiline,reply,COUNCIL_REPLY_CAPACITY)){
        free(command);free(reply);http_reply(client,409,"text/plain","Council unavailable\n",20);return;
    }
    free(command);
    if(!strncmp(reply,"ERROR",5))code=409;
    http_reply(client,code,"text/plain",reply,strlen(reply));
    free(reply);
}

static void usage(void){
    fputs("usage: council-web --bind ADDRESS --port PORT --hub HOST --hub-port PORT "
          "--name NAME --key-file FILE --password-file FILE\n",stderr);
}

int main(int argc,char**argv){
    web_config config;
    const char *bind=NULL,*key_file=NULL,*password_file=NULL;
    char password[384];
    uint16_t port=0;
    network_socket listener,client;
    int i;
    memset(&config,0,sizeof(config));
    for(i=1;i<argc;i++){
        if(!strcmp(argv[i],"--bind")&&++i<argc)bind=argv[i];
        else if(!strcmp(argv[i],"--port")&&++i<argc)port=(uint16_t)atoi(argv[i]);
        else if(!strcmp(argv[i],"--hub")&&++i<argc)snprintf(config.hub.host,sizeof(config.hub.host),"%s",argv[i]);
        else if(!strcmp(argv[i],"--hub-port")&&++i<argc)config.hub.port=(uint16_t)atoi(argv[i]);
        else if(!strcmp(argv[i],"--name")&&++i<argc)snprintf(config.name,sizeof(config.name),"%s",argv[i]);
        else if(!strcmp(argv[i],"--key-file")&&++i<argc)key_file=argv[i];
        else if(!strcmp(argv[i],"--password-file")&&++i<argc)password_file=argv[i];
        else{usage();return 2;}
    }
    if(!bind||!port||!config.hub.host[0]||!config.hub.port||!config.name[0]||
       !key_file||!password_file||read_secret(key_file,config.hub.shared_key,
       sizeof(config.hub.shared_key))||read_secret(password_file,password,sizeof(password))||
       make_authorization(config.name,password,config.authorization,sizeof(config.authorization))){
        usage();return 2;
    }
    if(network_start())return 1;
    listener=network_listen(bind,port);
    if(listener==INVALID_NETWORK_SOCKET){fprintf(stderr,"cannot listen on %u\n",port);return 1;}
    fprintf(stderr,"Council web gateway listening on %s:%u\n",bind,port);
    while((client=accept(listener,NULL,NULL))!=INVALID_NETWORK_SOCKET){
        handle_request(client,&config);
        network_close(client);
    }
    network_close(listener);network_stop();return 0;
}
