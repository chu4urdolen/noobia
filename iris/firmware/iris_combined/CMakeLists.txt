cmake_minimum_required(VERSION 3.16)

# Arduino 3.3.12 lists ESP_I2S for selective compilation but omits its
# Kconfig toggle. Iris's microphone needs it, so select it at CMake scope.
set(CONFIG_ARDUINO_SELECTIVE_ESP_I2S 1)

# Keep the board code in iris_noob and reusable runtime/USB LAN in esp/common.
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../../../esp/common/idf_usb_net")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
# Keep Arduino startup from releasing controller memory owned by NimBLE.
add_compile_definitions(ARDUINO_ARCH_ESP32=1)
project(iris_combined)
