/* Host-only AOSP AVB model. All partition callbacks read workspace files.
 * No USB access, phone commands, storage writes or rollback writes exist.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/stat.h>
#include "libavb/libavb.h"

typedef struct { const char *stock; const char *boot; int retain_tail; int unlocked; } Context;

static int stock_path(Context *ctx, const char *name, char *path, size_t capacity) {
    const char *leaves[] = {"boot", "vendor_boot", "vbmeta", "vbmeta_system", "vbmeta_vendor", NULL};
    for (int i = 0; leaves[i]; i++) {
        char partition[64];
        snprintf(partition, sizeof(partition), "%s_a", leaves[i]);
        if (!strcmp(name, partition)) {
            return snprintf(path, capacity, "%s/%s.img", ctx->stock, leaves[i]) < (int)capacity;
        }
    }
    return 0;
}

static AvbIOResult size_of(AvbOps *ops, const char *name, uint64_t *size) {
    Context *ctx = ops->user_data;
    char path[4096];
    if (!stock_path(ctx, name, path, sizeof(path))) return AVB_IO_RESULT_ERROR_NO_SUCH_PARTITION;
    struct stat st;
    if (stat(path, &st)) return AVB_IO_RESULT_ERROR_IO;
    *size = !strcmp(name, "boot_a") ? 67108864 : (uint64_t)st.st_size;
    return AVB_IO_RESULT_OK;
}

static int overlay(const char *path, uint64_t offset, size_t count, void *buffer) {
    struct stat st;
    if (stat(path, &st)) return 0;
    if (offset >= (uint64_t)st.st_size) return 1;
    size_t available = (uint64_t)st.st_size - offset;
    if (available > count) available = count;
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    int valid = !fseek(file, (long)offset, SEEK_SET) && fread(buffer, 1, available, file) == available;
    fclose(file);
    return valid;
}

static AvbIOResult read_partition(AvbOps *ops, const char *name, int64_t offset,
                                 size_t count, void *buffer, size_t *read_count) {
    Context *ctx = ops->user_data;
    uint64_t size;
    AvbIOResult result = size_of(ops, name, &size);
    if (result != AVB_IO_RESULT_OK) return result;
    if (offset < 0) offset += (int64_t)size;
    if (offset < 0 || (uint64_t)offset > size) return AVB_IO_RESULT_ERROR_RANGE_OUTSIDE_PARTITION;
    if (count > size - offset) count = size - offset;
    memset(buffer, 0, count);
    char path[4096];
    if (!stock_path(ctx, name, path, sizeof(path))) return AVB_IO_RESULT_ERROR_NO_SUCH_PARTITION;
    if (!strcmp(name, "boot_a")) {
        if (ctx->retain_tail && !overlay(path, offset, count, buffer)) return AVB_IO_RESULT_ERROR_IO;
        if (!overlay(ctx->boot, offset, count, buffer)) return AVB_IO_RESULT_ERROR_IO;
    } else if (!overlay(path, offset, count, buffer)) return AVB_IO_RESULT_ERROR_IO;
    *read_count = count;
    return AVB_IO_RESULT_OK;
}

static AvbIOResult trust_root(AvbOps *ops, const uint8_t *key, size_t length,
                            const uint8_t *metadata, size_t metadata_length, bool *trusted) {
    (void)ops; (void)key; (void)length; (void)metadata; (void)metadata_length;
    *trusted = true; /* Model assumption: trust the internally verified stock root key. */
    return AVB_IO_RESULT_OK;
}
static AvbIOResult rollback(AvbOps *ops, size_t location, uint64_t *value) {
    (void)ops; (void)location; *value = 0; return AVB_IO_RESULT_OK;
}
static AvbIOResult unlocked(AvbOps *ops, bool *value) {
    *value = ((Context *)ops->user_data)->unlocked; return AVB_IO_RESULT_OK;
}
static AvbIOResult guid(AvbOps *ops, const char *name, char *buffer, size_t size) {
    (void)ops; (void)name;
    if (size < 37) return AVB_IO_RESULT_ERROR_IO;
    strcpy(buffer, "00000000-0000-0000-0000-000000000000");
    return AVB_IO_RESULT_OK;
}

int main(int argc, char **argv) {
    if (argc != 5) { fprintf(stderr, "usage: model STOCK_DIRECTORY BOOT_IMAGE RETAIN_STOCK_TAIL UNLOCKED\n"); return 2; }
    Context ctx = {argv[1], argv[2], atoi(argv[3]), atoi(argv[4])};
    AvbOps ops = {0};
    ops.user_data = &ctx;
    ops.read_from_partition = read_partition;
    ops.get_size_of_partition = size_of;
    ops.validate_vbmeta_public_key = trust_root;
    ops.read_rollback_index = rollback;
    ops.read_is_device_unlocked = unlocked;
    ops.get_unique_guid_for_partition = guid;
    const char *requested[] = {"boot", NULL};
    AvbSlotVerifyData *data = NULL;
    AvbSlotVerifyResult result = avb_slot_verify(&ops, requested, "_a",
        ctx.unlocked ? AVB_SLOT_VERIFY_FLAGS_ALLOW_VERIFICATION_ERROR : AVB_SLOT_VERIFY_FLAGS_NONE,
        AVB_HASHTREE_ERROR_MODE_EIO, &data);
    size_t loaded = data ? data->num_loaded_partitions : 0;
    printf("{\"result\":\"%s\",\"boot_partitions_loaded\":%zu,\"slot_data_returned\":%s,\"unlocked_model\":%s,\"retained_stock_tail_model\":%s}\n",
        avb_slot_verify_result_to_string(result), loaded, data ? "true" : "false",
        ctx.unlocked ? "true" : "false", ctx.retain_tail ? "true" : "false");
    if (data) avb_slot_verify_data_free(data);
    return 0;
}
