#include "contact_book.h"
#include "service_config.h"
#include <stdio.h>
int main(int n,char**v){service_config c;contact_book b;char e[256];if(n!=2){fputs("usage: council-config-check SERVICE.conf\n",stderr);return 2;}if(service_config_load(v[1],&c,e,sizeof(e))){fprintf(stderr,"service config: %s\n",e);return 1;}if(contact_book_load(c.contacts_path,&b,e,sizeof(e))){fprintf(stderr,"contact book: %s\n",e);return 1;}printf("configuration OK: %s, %lu contacts\n",c.name,(unsigned long)b.count);return 0;}
