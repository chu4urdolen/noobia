#ifndef LYNX_RAM_LOG_READER_H
#define LYNX_RAM_LOG_READER_H
typedef __UINT8_TYPE__ u8;
typedef __UINT32_TYPE__ u32;
typedef __UINTPTR_TYPE__ uptr;
/* ABI from the reviewed V6 DA payload source. */
struct lynx_channel {
    int (*read)(u8 *, u32 *);
    int (*write)(u8 *, u32);
    int (*log_to_pc)(const u8 *, u32);
    int (*log_to_uart)(const u8 *, u32);
};
#define LYNX_PSTORE_ADDRESS ((uptr)0x48090000)
#define LYNX_PSTORE_BYTES ((u32)0xe0000)
#define LYNX_READER_MARKER "LYNX_RAM_LOG_READER_V1\n"
int lynx_reader_probe(struct lynx_channel *, const char *);
int lynx_reader_pstore(struct lynx_channel *, const char *);
#endif
