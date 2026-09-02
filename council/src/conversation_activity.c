#include "conversation_activity.h"
#include <errno.h>
#include <stdio.h>
#include <sys/stat.h>
#include <time.h>
int conversation_activity_mark(const char*path){FILE*file;char temporary[1024];time_t now=time(NULL);if(!path||!path[0])return -1;snprintf(temporary,sizeof(temporary),"%s.new",path);file=fopen(temporary,"w");if(!file)return -1;fprintf(file,"%lld\n",(long long)now);if(fclose(file))return -1;
#ifdef _WIN32
remove(path);
#endif
return rename(temporary,path);}
int conversation_activity_clear(const char*path){FILE*file;char temporary[1024];if(!path||!path[0])return-1;snprintf(temporary,sizeof(temporary),"%s.new",path);file=fopen(temporary,"w");if(!file)return-1;if(fputs("-1\n",file)<0||fclose(file))return-1;return rename(temporary,path);}
int conversation_activity_remaining(const char*path,const char*log_path,int lease){FILE*file;long long recorded=0;time_t now=time(NULL);struct stat info;if(path&&path[0]&&(file=fopen(path,"r"))!=NULL){if(fscanf(file,"%lld",&recorded)!=1)recorded=0;fclose(file);}if(recorded<0)return 0;if(!recorded&&log_path&&log_path[0]&&!stat(log_path,&info))recorded=(long long)info.st_mtime;if(!recorded)return 0;if(now<=(time_t)recorded)return lease;if(now-(time_t)recorded>=lease)return 0;return lease-(int)(now-(time_t)recorded);}
