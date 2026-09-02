#include "authentication.h"
#include "sha256.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#endif
static void hex(const uint8_t*b,size_t n,char*o){static const char d[]="0123456789abcdef";size_t i;for(i=0;i<n;i++){o[i*2]=d[b[i]>>4];o[i*2+1]=d[b[i]&15];}o[n*2]=0;}
int authentication_nonce(char o[33]){uint8_t b[16];
#ifdef _WIN32
if(BCryptGenRandom(NULL,b,sizeof(b),BCRYPT_USE_SYSTEM_PREFERRED_RNG))return -1;
#else
FILE*f=fopen("/dev/urandom","rb");if(!f)return -1;if(fread(b,1,sizeof(b),f)!=sizeof(b)){fclose(f);return -1;}fclose(f);
#endif
hex(b,16,o);return 0;}
void authentication_digest(const char*k,const char*n,const char*x,char o[65]){char m[256];uint8_t d[32];snprintf(m,sizeof(m),"%s|%s",n,x);hmac_sha256((const uint8_t*)k,strlen(k),(const uint8_t*)m,strlen(m),d);hex(d,32,o);}
int authentication_matches(const char*a,const char*b){unsigned char d=0;size_t i,n=strlen(a);if(n!=strlen(b))return 0;for(i=0;i<n;i++)d|=(unsigned char)(a[i]^b[i]);return d==0;}
