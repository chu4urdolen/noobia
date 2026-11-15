file(GLOB_RECURSE NOOB_COMMON_SOURCES
     "${CMAKE_CURRENT_LIST_DIR}/../../../../esp/common/src/*.cpp")
file(GLOB_RECURSE IRIS_SOURCES
     "${CMAKE_CURRENT_LIST_DIR}/../../iris_noob/src/*.cpp")

idf_component_register(
    SRCS "iris_combined.cpp" ${NOOB_COMMON_SOURCES} ${IRIS_SOURCES}
    INCLUDE_DIRS "."
                 "${CMAKE_CURRENT_LIST_DIR}/../../../../esp/common/src"
                 "${CMAKE_CURRENT_LIST_DIR}/../../iris_noob"
                 "${CMAKE_CURRENT_LIST_DIR}/../../iris_noob/src"
    REQUIRES espressif__arduino-esp32 espressif__esp32-camera
             espressif__network_provisioning h2zero__esp-nimble-cpp idf_usb_net)

# Arduino CLI builds these existing sources without IDF's warning-as-error
# policy. Keep diagnostics visible while migrating rather than editing shared
# runtime files just to satisfy a different compiler configuration.
target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wno-error=misleading-indentation -Wno-error=format)
target_compile_definitions(${COMPONENT_LIB} PRIVATE BOARD_HAS_PSRAM=1 NOOB_USE_NIMBLE=1)
