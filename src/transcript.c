#define _POSIX_C_SOURCE 200809L
#include "transcript.h"
#include <stdio.h>
#include <string.h>
#include <time.h>
int transcript_append(const char *path,const char *speaker,const char *event,const char *message){FILE*f;time_t now=time(NULL);struct tm tm_value;char stamp[32];if(!path||!path[0])return 0;
#ifdef _WIN32
gmtime_s(&tm_value,&now);
#else
gmtime_r(&now,&tm_value);
#endif
strftime(stamp,sizeof(stamp),"%Y-%m-%dT%H:%M:%SZ",&tm_value);f=fopen(path,"a");if(!f)return -1;fprintf(f,"%s\t%s\t%s\t%s\n",stamp,speaker,event,message);fclose(f);return 0;}

int transcript_stream_since(const char *path,long offset,network_socket socket,long *next_offset){FILE*f;char line[8192],out[8224];long end;if(offset<0)offset=0;f=fopen(path,"r");if(!f){*next_offset=0;return 0;}if(fseek(f,0,SEEK_END)){fclose(f);return-1;}end=ftell(f);if(offset>end)offset=0;if(fseek(f,offset,SEEK_SET)){fclose(f);return-1;}while(fgets(line,sizeof(line),f)){line[strcspn(line,"\r\n")]=0;snprintf(out,sizeof(out),"EVENT %s\n",line);if(network_send(socket,out)){fclose(f);return-1;}}*next_offset=ftell(f);fclose(f);return 0;}

static int is_grant_for(const char*line,const char*participant){const char*p=strstr(line,"\tgrant\t");const char*q=strstr(line,"\toffline-grant\t");const char*value;if(!p&&!q)return 0;value=(p?p:q)+strlen(p?"\tgrant\t":"\toffline-grant\t");if(q){const char*arrow=strstr(value," -> ");value=arrow?arrow+4:value;}return !strncmp(value,participant,strlen(participant))&&(value[strlen(participant)]=='\n'||value[strlen(participant)]=='\r'||value[strlen(participant)]==0);}
int transcript_stream_context(const char*path,const char*participant,network_socket socket){FILE*f;char line[8192],out[8224];long previous=0,current=0,start=0;f=fopen(path,"r");if(!f)return 0;while(1){long position=ftell(f);if(!fgets(line,sizeof(line),f))break;if(is_grant_for(line,participant)){previous=current;current=position;}}start=previous?previous:0;if(fseek(f,start,SEEK_SET)){fclose(f);return-1;}while(fgets(line,sizeof(line),f)){line[strcspn(line,"\r\n")]=0;snprintf(out,sizeof(out),"CONTEXT %s\n",line);if(network_send(socket,out)){fclose(f);return-1;}}fclose(f);return 0;}
int transcript_last_speaker(const char*path,char*speaker,size_t speaker_size){FILE*f;char line[8192];speaker[0]=0;f=fopen(path,"r");if(!f)return 0;while(fgets(line,sizeof(line),f)){char*p,*q,*value;if(strstr(line,"\tconversation-end\t")){speaker[0]=0;continue;}p=strstr(line,"\tgrant\t");q=strstr(line,"\toffline-grant\t");if(!p&&!q)continue;value=(p?p:q)+strlen(p?"\tgrant\t":"\toffline-grant\t");if(q){char*arrow=strstr(value," -> ");if(arrow)value=arrow+4;}value[strcspn(value,"\r\n")]=0;if(strstr(value," -> "))value=strstr(value," -> ")+4;snprintf(speaker,speaker_size,"%s",value);}fclose(f);return 0;}
