/* Host-only fake channel: protocol, completeness, abort, and fixed-region tests. */
#include "reader.h"
#ifdef LYNX_ARM_TEST
#include "test_runtime.h"
#else
#include <assert.h>
#include <stdio.h>
#include <string.h>
#endif
static u8 fixture[LYNX_PSTORE_BYTES], received[LYNX_PSTORE_BYTES];
static u32 count, reads, writes, expected, packets;
static int fail_read, fail_write, malformed;
const u8 *lynx_fixture_pstore(void) { return fixture; }
static int fake_read(u8 *buffer, u32 *size)
{
    reads++;
    assert(*size == 64);
    if ((int)reads == fail_read) return 1;
    memcpy(buffer, malformed ? "NO" : "OK", 3);
    *size = 3;
    return 0;
}
static int fake_write(u8 *buffer, u32 size)
{
    writes++;
    if ((int)writes == fail_write) return 1;
    if (writes == 1) {
        assert(size > 100 && buffer[size - 1] == 0);
        assert(strstr((char *)buffer, "CMD:UPLOAD-FILE"));
    } else if (writes == 2) {
        assert(strcmp((char *)buffer, expected == LYNX_PSTORE_BYTES ? "OK@0xe0000" : "OK@0x17") == 0);
    } else if (writes == 3 || (writes & 1)) {
        assert(size == 3 && memcmp(buffer, "OK", 3) == 0);
    } else {
        assert(size > 0 && size <= 0x1000 && count + size <= expected);
        memcpy(received + count, buffer, size);
        count += size;
        packets++;
    }
    return 0;
}
static struct lynx_channel channel = {fake_read, fake_write, 0, 0};
static void reset(u32 length)
{
    count = reads = writes = packets = 0;
    expected = length;
    fail_read = fail_write = malformed = 0;
    memset(received, 0, sizeof(received));
}
int main(void)
{
    for (u32 i = 0; i < sizeof(fixture); i++) fixture[i] = (u8)(i * 17 + i / 255);
    reset(0x17);
    assert(lynx_reader_probe(&channel, "ignored") == 0);
    assert(count == 0x17 && memcmp(received, LYNX_READER_MARKER, count) == 0);
    reset(LYNX_PSTORE_BYTES);
    assert(lynx_reader_pstore(&channel, "<address>0</address><length>0xffffffff</length>") == 0);
    assert(count == sizeof(fixture) && packets == 224 && reads == 450);
    assert(memcmp(received, fixture, sizeof(fixture)) == 0);
    for (int stage = 1; stage <= 5; stage++) {
        reset(LYNX_PSTORE_BYTES); fail_write = stage;
        assert(lynx_reader_pstore(&channel, 0) != 0 && (int)writes == stage);
        reset(LYNX_PSTORE_BYTES); fail_read = stage;
        assert(lynx_reader_pstore(&channel, 0) != 0 && (int)reads == stage);
    }
    reset(LYNX_PSTORE_BYTES); malformed = 1;
    assert(lynx_reader_pstore(&channel, 0) != 0 && count == 0 && reads == 1);
    reset(LYNX_PSTORE_BYTES);
    assert(lynx_reader_pstore(0, 0) != 0 && writes == 0);
    struct lynx_channel missing = {0};
    assert(lynx_reader_pstore(&missing, 0) != 0 && writes == 0);
    puts("Fixed-region export, 224 packets, marker, ignored address input, and 13 abort cases passed.");
    return 0;
}
