/* Native Linux interface to the original stock connectivity drivers.
 * Reads fixed RAM/config files; writes only /dev/wmtWifi and stdout.
 * No partition writes, calibration synthesis, debug ioctls, or mmap.
 */
static long call(long n,long a,long b,long c,long d) {
 register long x0 __asm__("x0")=a; register long x1 __asm__("x1")=b;
 register long x2 __asm__("x2")=c; register long x3 __asm__("x3")=d;
 register long x8 __asm__("x8")=n;
 __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1),"r"(x2),"r"(x3),"r"(x8) : "memory");return x0;
}
static int same(const char*a,const char*b) {while(*a && *a==*b){a++;b++;}return *a==*b;}
static long length(const char*s){long n=0;while(s[n])n++;return n;}
static void message(const char*s){call(64,1,(long)s,length(s),0);}
static long open_fixed(const char*p,long flags){return call(56,-100,(long)p,flags|02000000,0);}
static int kind(long fd,unsigned int expected){unsigned long data[18];long s=call(80,fd,(long)data,0,0);return s==0 && (*(unsigned int*)((char*)data+16)&0170000)==expected;}
/* A nonempty .data segment gives this freestanding ELF a mapped writable
 * first page; all payload bytes are overwritten before a driver write. */
static unsigned char buffer[32768+13] = {1};
static int submit(const char*file,const char*header,long minimum){
 long input=open_fixed(file,0);if(input<0)return 120;
 if(!kind(input,0100000)){call(57,input,0,0,0);return 121;}
 long prefix=length(header);for(long i=0;i<prefix;i++)buffer[i]=header[i];
 long size=0;
 while(size<32768){long n=call(63,input,(long)(buffer+prefix+size),32768-size,0);if(n<0){call(57,input,0,0,0);return 122;}if(n==0)break;size+=n;}
 unsigned char extra;long tail=call(63,input,(long)&extra,1,0);call(57,input,0,0,0);
 if(tail!=0 || size<minimum)return 123;
 long output=open_fixed("/dev/wmtWifi",1);if(output<0)return 124;
 if(!kind(output,0020000)){call(57,output,0,0,0);return 125;}
 /* One complete write: the driver's WR-BUF parser cannot accept chunks. */
 long n=call(64,output,(long)buffer,prefix+size,0);call(57,output,0,0,0);
 return n==prefix+size?0:126;
}
int main(long argc,char**argv){
 if(argc!=2)return 110;
 if(same(argv[1],"--chip")){
  long fd=open_fixed("/dev/conninfra_dev",0);if(fd<0)return 111;
  if(!kind(fd,0020000)){call(57,fd,0,0,0);return 112;}
  /* GET_CHIP_ID returns the integer directly in this driver, not a pointer. */
  long chip=call(29,fd,0x8004c200,0,0);call(57,fd,0,0,0);
  if(chip!=0x6983)return 113;message("LYNX_CONNECTIVITY_CHIP_MT6983\n");return 0;
 }
 if(same(argv[1],"--nvram"))return submit("/run/lynx/calibration/WIFI","WR-BUF:NVRAM",128);
 if(same(argv[1],"--drvcfg"))return submit("/odm/etc/wifi/wifi.cfg","WR-BUF:DRVCFG",1);
 if(same(argv[1],"--station")){
  long fd=open_fixed("/dev/wmtWifi",1);if(fd<0)return 114;
  if(!kind(fd,0020000)){call(57,fd,0,0,0);return 115;}
  long n=call(64,fd,(long)"S",1,0);call(57,fd,0,0,0);return n==1?0:116;
 }
 return 117;
}
