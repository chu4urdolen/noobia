#include "camera_common.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void)
{
    const char *camera = camera_setting("ROSE_RPICAM_STILL", "/usr/bin/rpicam-still");
    char output[PATH_MAX];
    char *arguments[] = {
        (char *)camera, "--camera", "0", "--rotation", "180", "--nopreview",
        "--timeout", "1s", "--width", "2028", "--height", "1520", "--quality", "93",
        "--output", output, NULL
    };
    if (camera_temp_path(output, sizeof(output), "snapshot", ".jpg") != 0) {
        perror("temporary snapshot");
        return EXIT_FAILURE;
    }
    if (camera_run(arguments, 30) != 0 || !camera_file_ready(output)) {
        unlink(output);
        fprintf(stderr, "Nyx snapshot failed\n");
        return EXIT_FAILURE;
    }
    puts(output);
    return EXIT_SUCCESS;
}
