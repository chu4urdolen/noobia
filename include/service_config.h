#ifndef NOOBIA_SERVICE_CONFIG_H
#define NOOBIA_SERVICE_CONFIG_H
#include <stddef.h>
#include <stdint.h>
#include "contact_book.h"

#define COUNCIL_PATH_LENGTH 512
typedef struct {
    char name[COUNCIL_NAME_LENGTH];
    contact_role role;
    char bind_address[COUNCIL_HOST_LENGTH];
    uint16_t human_port;
    uint16_t ai_port;
    int is_hub;
    char hub_host[COUNCIL_HOST_LENGTH];
    uint16_t hub_port;
    char own_key[COUNCIL_KEY_LENGTH];
    char contacts_path[COUNCIL_PATH_LENGTH];
    char transcript_path[COUNCIL_PATH_LENGTH];
    char inbox_path[COUNCIL_PATH_LENGTH];
    char summary_path[COUNCIL_PATH_LENGTH];
    char activity_path[COUNCIL_PATH_LENGTH];
    char files_directory[COUNCIL_PATH_LENGTH];
    uint64_t max_file_bytes;
    int presence_seconds;
} service_config;
int service_config_load(const char *path, service_config *config,
                        char *error, size_t error_size);
#endif

