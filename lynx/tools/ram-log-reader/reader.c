/* Fixed RAM export only. No storage API, security policy, or writable address input. */
#include "reader.h"
#define STATUS_ERROR ((int)0xc0010001)
#define PACKET_BYTES 0x1000u
static const char marker[] = LYNX_READER_MARKER;
static const char pstore_header[] =
    "<?xml version=\"1.0\" encoding=\"utf-8\"?><host><version>1.0</version>"
    "<command>CMD:UPLOAD-FILE</command><arg><checksum>CHK_NO</checksum>"
    "<info>Lynx fixed pstore RAM export</info><target_file>lynx-pstore-raw.bin</target_file>"
    "<packet_length>0x1000</packet_length></arg></host>";
static const char probe_header[] =
    "<?xml version=\"1.0\" encoding=\"utf-8\"?><host><version>1.0</version>"
    "<command>CMD:UPLOAD-FILE</command><arg><checksum>CHK_NO</checksum>"
    "<info>Lynx RAM reader diagnostic marker</info><target_file>lynx-reader-marker.txt</target_file>"
    "<packet_length>0x1000</packet_length></arg></host>";
static const char ok[] = "OK";
static const char pstore_length[] = "OK@0xe0000";
static const char probe_length[] = "OK@0x17";
_Static_assert(sizeof(marker) - 1 == 0x17, "Probe wire size changed");

static int acknowledged(struct lynx_channel *channel)
{
    u8 response[64] = {0};
    u32 size = sizeof(response);
    if (channel->read(response, &size) != 0) return 0;
    return (size == 2 || (size == 3 && response[2] == 0))
        && response[0] == 'O' && response[1] == 'K';
}

static int export_region(struct lynx_channel *channel, const char *header, u32 header_bytes,
                         const char *length, u32 length_bytes, const u8 *data, u32 bytes)
{
    if (!channel || !channel->read || !channel->write) return STATUS_ERROR;
    if (channel->write((u8 *)header, header_bytes) != 0) return STATUS_ERROR;
    if (channel->write((u8 *)length, length_bytes) != 0 || !acknowledged(channel)) return STATUS_ERROR;
    if (channel->write((u8 *)ok, sizeof(ok)) != 0 || !acknowledged(channel)) return STATUS_ERROR;
    for (u32 offset = 0; offset < bytes;) {
        u32 chunk = bytes - offset;
        if (chunk > PACKET_BYTES) chunk = PACKET_BYTES;
        if (channel->write((u8 *)(data + offset), chunk) != 0 || !acknowledged(channel)) return STATUS_ERROR;
        if (channel->write((u8 *)ok, sizeof(ok)) != 0 || !acknowledged(channel)) return STATUS_ERROR;
        offset += chunk;
    }
    return 0; /* The DA dispatcher supplies CMD:END/START after this callback. */
}

int lynx_reader_probe(struct lynx_channel *channel, const char *xml)
{
    (void)xml; /* No caller-controlled region or length. */
    return export_region(channel, probe_header, sizeof(probe_header), probe_length,
                         sizeof(probe_length), (const u8 *)marker, sizeof(marker) - 1);
}

int lynx_reader_pstore(struct lynx_channel *channel, const char *xml)
{
    (void)xml;
#ifdef LYNX_HOST_TEST
    extern const u8 *lynx_fixture_pstore(void);
    const u8 *data = lynx_fixture_pstore();
#else
    const u8 *data = (const u8 *)LYNX_PSTORE_ADDRESS;
#endif
    return export_region(channel, pstore_header, sizeof(pstore_header), pstore_length,
                         sizeof(pstore_length), data, LYNX_PSTORE_BYTES);
}
