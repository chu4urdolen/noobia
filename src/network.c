#define _POSIX_C_SOURCE 200112L
#include "network.h"
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <ws2tcpip.h>
#else
#include <netdb.h>
#include <unistd.h>
#include <sys/socket.h>
#endif
int network_start(void){
#ifdef _WIN32
WSADATA d;return WSAStartup(MAKEWORD(2,2),&d);
#else
return 0;
#endif
}
void network_stop(void){
#ifdef _WIN32
WSACleanup();
#endif
}
void network_close(network_socket s){
#ifdef _WIN32
closesocket(s);
#else
close(s);
#endif
}
int network_connect(const char*h,uint16_t p,network_socket*out){struct addrinfo q,*a,*i;char ps[16];memset(&q,0,sizeof(q));q.ai_family=AF_UNSPEC;q.ai_socktype=SOCK_STREAM;snprintf(ps,sizeof(ps),"%u",p);if(getaddrinfo(h,ps,&q,&a))return -1;for(i=a;i;i=i->ai_next){*out=socket(i->ai_family,i->ai_socktype,i->ai_protocol);if(*out!=INVALID_NETWORK_SOCKET&&!connect(*out,i->ai_addr,(int)i->ai_addrlen))break;if(*out!=INVALID_NETWORK_SOCKET)network_close(*out);}freeaddrinfo(a);return i?0:-1;}
network_socket network_listen(const char*h,uint16_t p){struct addrinfo q,*a,*i;char ps[16];network_socket s=INVALID_NETWORK_SOCKET;int yes=1;memset(&q,0,sizeof(q));q.ai_family=AF_UNSPEC;q.ai_socktype=SOCK_STREAM;q.ai_flags=AI_PASSIVE;snprintf(ps,sizeof(ps),"%u",p);if(getaddrinfo(h,ps,&q,&a))return s;for(i=a;i;i=i->ai_next){s=socket(i->ai_family,i->ai_socktype,i->ai_protocol);if(s==INVALID_NETWORK_SOCKET)continue;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,(const char*)&yes,sizeof(yes));if(!bind(s,i->ai_addr,(int)i->ai_addrlen)&&!listen(s,32))break;network_close(s);s=INVALID_NETWORK_SOCKET;}freeaddrinfo(a);return s;}
int network_send_bytes(network_socket s,const void*data,size_t n){const char*d=data;while(n){int z=send(s,d,(int)n,0);if(z<=0)return -1;d+=z;n-=(size_t)z;}return 0;}
int network_read_bytes(network_socket s,void*data,size_t n){char*d=data;while(n){int z=recv(s,d,(int)n,0);if(z<=0)return -1;d+=z;n-=(size_t)z;}return 0;}
int network_send(network_socket s,const char*d){return network_send_bytes(s,d,strlen(d));}
int network_read_line(network_socket s,char*b,size_t n){size_t u=0;char x;while(u+1<n){int z=recv(s,&x,1,0);if(z<=0)return -1;if(x=='\n'){b[u]=0;return (int)u;}if(x!='\r')b[u++]=x;}return -1;}
