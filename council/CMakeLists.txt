cmake_minimum_required(VERSION 3.16)
project(noobia_council C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(MSVC)
  add_compile_options(/W4)
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_library(council_core
  src/authentication.c
  src/arbitration.c
  src/contact_book.c
  src/conversation_activity.c
  src/conversation_memory.c
  src/file_commands.c
  src/file_storage.c
  src/network.c
  src/presence.c
  src/protocol.c
  src/service_config.c
  src/sha256.c
  src/transcript.c)
target_include_directories(council_core PUBLIC include)

add_executable(council-config-check src/config_check.c)
target_link_libraries(council-config-check PRIVATE council_core)

add_executable(noobia-council src/council_service.c)
target_link_libraries(noobia-council PRIVATE council_core)

add_executable(councilctl src/council_client.c)
target_link_libraries(councilctl PRIVATE council_core)

add_executable(council-agent src/council_initiator.c)
target_link_libraries(council-agent PRIVATE council_core)

if(WIN32)
  target_link_libraries(council_core PUBLIC ws2_32 bcrypt)
else()
  find_package(Threads REQUIRED)
  target_link_libraries(noobia-council PRIVATE Threads::Threads)
endif()

enable_testing()
add_test(NAME configuration COMMAND council-config-check
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/nexus.conf)
set_tests_properties(configuration PROPERTIES
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(council-send-file src/council_file_sender.c)
target_link_libraries(council-send-file PRIVATE council_core)

add_executable(council-live src/council_live.c)
target_link_libraries(council-live PRIVATE council_core)

add_executable(council-web src/council_web.c src/web_page.c)
target_link_libraries(council-web PRIVATE council_core)

if(NOT WIN32)
  add_executable(council-codex-bridge src/council_codex_bridge.c)
  target_link_libraries(council-codex-bridge PRIVATE council_core)
endif()
