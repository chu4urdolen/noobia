# Iris command reference

Generated from the source registry and test policies. Do not hand-edit.

## Protocol controls

`PING`, `INFO`, `CAPS`, `LOAD`, `RUN`, `START_THREAD`, `STOP`, `STOP_THREAD`, `RESET_VM`, `CALL`, `CALL_TEXT`, `CALL_MIXED`, `STATUS`, `THREAD_STATUS`.

These control/inspect the runtime. START_THREAD/STOP_THREAD/THREAD_STATUS are
aliases for RUN/STOP/STATUS; they do not select individual native sensor threads.

## Native functions

Invoke by name or ID with CALL, CALL_TEXT or CALL_MIXED. VM SYS/SYS_MIXED uses
the same registry. Updated sequence channels support numeric plus ASCII
arguments and optional bit forwarding. See CHANNEL_CALLS.md for the required
firmware version and live-test results.
Live CAPS is authoritative: a source entry does not guarantee enabled hardware.

| ID | Function | Arguments | Test mode | Availability |
| --- | --- | --- | --- | --- |
| 1 | TIME_NOW | numbers | boot_read_only | registered_when_service_enabled |
| 2 | TIME_RESET | numbers | destructive_opt_in | registered_when_service_enabled |
| 3 | SEQUENCE_SET | numbers_or_text_config_or_mixed | on_demand | registered_when_service_enabled |
| 4 | SEQUENCE_START | numbers | on_demand | registered_when_service_enabled |
| 5 | SEQUENCE_STOP | numbers | on_demand | registered_when_service_enabled |
| 6 | SEQUENCE_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 7 | SEQUENCE_CLEAR | numbers | on_demand | registered_when_service_enabled |
| 8 | SEQUENCE_POP | numbers | on_demand | registered_when_service_enabled |
| 9 | SEQUENCE_QUEUE_SIZE | numbers | boot_read_only | registered_when_service_enabled |
| 10 | SEQUENCE_QUEUE_CLEAR | numbers | on_demand | registered_when_service_enabled |
| 11 | SEQUENCE_BUSY | numbers | boot_read_only | registered_when_service_enabled |
| 12 | SEQUENCE_FIELD | numbers | on_demand | registered_when_service_enabled |
| 13 | SELF_TEST | numbers | on_demand | registered_when_service_enabled |
| 100 | CAMERA_CAPTURE | numbers | manual_fixture | registered_when_service_enabled |
| 101 | STORAGE_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 105 | SD_DELETE | ascii | destructive_opt_in | registered_when_service_enabled |
| 106 | SD_LIST | ascii | on_demand | registered_when_service_enabled |
| 110 | WIFI_SCAN | numbers | on_demand | registered_when_service_enabled |
| 111 | WIFI_RSSI | numbers | on_demand | registered_when_service_enabled |
| 114 | WIFI_CONNECT | numbers | on_demand | registered_when_service_enabled |
| 115 | WIFI_DISCONNECT | numbers | on_demand | registered_when_service_enabled |
| 116 | WIFI_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 117 | WIFI_CREDENTIALS_SET | ascii | destructive_opt_in | registered_when_service_enabled |
| 120 | MIC_LEVEL | numbers | boot_sensor | registered_when_service_enabled |
| 121 | MIC_ABOVE | numbers | boot_sensor | registered_when_service_enabled |
| 122 | AUDIO_RECORD | numbers | manual_fixture | registered_when_service_enabled |
| 130 | LED_RGB | numbers | manual_fixture | registered_when_service_enabled |
| 131 | LED_SIGNAL | numbers | manual_fixture | registered_when_service_enabled |
| 132 | LED_EXTERNAL | numbers | manual_fixture | registered_when_service_enabled |
| 140 | VM_SAVE | ascii | on_demand | registered_when_service_enabled |
| 141 | VM_LOAD_SAVED | ascii | on_demand | registered_when_service_enabled |
| 142 | VM_LIST_SAVED | ascii | on_demand | registered_when_service_enabled |
| 143 | VM_DELETE_SAVED | ascii | destructive_opt_in | registered_when_service_enabled |
| 144 | VM_LAST_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 145 | VM_LAST_CLEAR | numbers | destructive_opt_in | registered_when_service_enabled |
| 160 | BLE_SCAN | numbers | on_demand | registered_when_service_enabled |
| 161 | BLE_PEER_SET | ascii | destructive_opt_in | registered_when_service_enabled |
| 162 | BLE_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 170 | GPIO_AUDIT | numbers | disabled | disabled_in_current_build |
| 171 | GPIO_INSPECT | numbers | disabled | disabled_in_current_build |
| 172 | GPIO_PULL_TEST | numbers | disabled | disabled_in_current_build |
| 190 | TEMP_HUMIDITY_READ | numbers | boot_sensor | registered_when_service_enabled |
| 191 | ADC_READ | numbers | boot_sensor | registered_when_service_enabled |
| 192 | LIGHT_READ | numbers | boot_sensor | registered_when_service_enabled |
| 193 | IR_SEND | numbers | manual_fixture | registered_when_service_enabled |
| 194 | IR_READ | numbers | manual_fixture | registered_when_service_enabled |
| 195 | IR_LOOPBACK | numbers | manual_fixture | registered_when_service_enabled |
| 196 | ULTRASONIC_READ | numbers | boot_sensor | registered_when_service_enabled |
| 197 | LED_BLUE | numbers | manual_fixture | registered_when_service_enabled |
| 198 | LED_RED | numbers | manual_fixture | registered_when_service_enabled |
| 199 | DISTANCE_MM | numbers | boot_sensor | registered_when_service_enabled |
| 200 | BLUE_BLINK_SEQUENCE | numbers | manual_fixture | registered_when_service_enabled |
| 201 | POLICE_SEQUENCE | numbers | manual_fixture | registered_when_service_enabled |
| 202 | ULTRASONIC_CHANGE_START | numbers | on_demand | registered_when_service_enabled |
| 203 | ULTRASONIC_CHANGE_STOP | numbers | on_demand | registered_when_service_enabled |
| 204 | ULTRASONIC_CHANGE_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 205 | ULTRASONIC_CHANGE_POP | numbers | on_demand | registered_when_service_enabled |
| 206 | ULTRASONIC_CHANGE_POLL | numbers | on_demand | registered_when_service_enabled |
| 207 | LIGHT_CHANGE_START | numbers | on_demand | registered_when_service_enabled |
| 208 | LIGHT_CHANGE_STOP | numbers | on_demand | registered_when_service_enabled |
| 209 | LIGHT_CHANGE_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 210 | LIGHT_CHANGE_POP | numbers | on_demand | registered_when_service_enabled |
| 211 | LIGHT_CHANGE_POLL | numbers | on_demand | registered_when_service_enabled |
| 212 | MIC_RISE_START | numbers | on_demand | registered_when_service_enabled |
| 213 | MIC_RISE_STOP | numbers | on_demand | registered_when_service_enabled |
| 214 | MIC_RISE_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 215 | MIC_RISE_POP | numbers | on_demand | registered_when_service_enabled |
| 216 | MIC_RISE_POLL | numbers | on_demand | registered_when_service_enabled |
| 217 | CAMERA_SEQUENCE_STEP | numbers | manual_fixture | registered_when_service_enabled |
| 218 | CAMERA_SEQUENCE | numbers | manual_fixture | registered_when_service_enabled |
| 219 | IR_SEQUENCE_STEP | numbers | manual_fixture | registered_when_service_enabled |
| 220 | IR_SEQUENCE | numbers | manual_fixture | registered_when_service_enabled |
| 221 | RSSI_SNAPSHOT | numbers | manual_fixture | registered_when_service_enabled |
| 222 | IR_SNAPSHOT | numbers | manual_fixture | registered_when_service_enabled |
| 223 | ENV_SNAPSHOT | numbers | manual_fixture | registered_when_service_enabled |
| 224 | ENV_TEMPERATURE | numbers | on_demand | registered_when_service_enabled |
| 225 | ENV_HUMIDITY | numbers | on_demand | registered_when_service_enabled |
| 226 | IR_REPLAY | numbers | manual_fixture | registered_when_service_enabled |
| 230 | RSSI_THREAD_START | numbers_and_optional_ascii | on_demand | registered_when_service_enabled |
| 231 | RSSI_THREAD_STOP | numbers | on_demand | registered_when_service_enabled |
| 232 | RSSI_THREAD_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 233 | RSSI_THREAD_POP | numbers | on_demand | registered_when_service_enabled |
| 234 | RSSI_THREAD_POLL | numbers | on_demand | registered_when_service_enabled |
| 235 | IR_THREAD_START | numbers | on_demand | registered_when_service_enabled |
| 236 | IR_THREAD_STOP | numbers | on_demand | registered_when_service_enabled |
| 237 | IR_THREAD_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 238 | IR_THREAD_POP | numbers | on_demand | registered_when_service_enabled |
| 239 | IR_THREAD_POLL | numbers | on_demand | registered_when_service_enabled |
| 240 | ENV_THREAD_START | numbers_and_optional_ascii | on_demand | registered_when_service_enabled |
| 241 | ENV_THREAD_STOP | numbers | on_demand | registered_when_service_enabled |
| 242 | ENV_THREAD_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 243 | ENV_THREAD_POP | numbers | on_demand | registered_when_service_enabled |
| 244 | ENV_THREAD_POLL | numbers | on_demand | registered_when_service_enabled |
| 245 | RSSI_THREAD_FIELD | numbers | on_demand | registered_when_service_enabled |
| 246 | IR_THREAD_FIELD | numbers | on_demand | registered_when_service_enabled |
| 247 | ENV_THREAD_FIELD | numbers | on_demand | registered_when_service_enabled |
| 248 | IR_DICT_REMEMBER | ascii | manual_fixture | registered_when_service_enabled |
| 249 | IR_DICT_STATUS | numbers | manual_fixture | registered_when_service_enabled |
| 250 | IR_CAPTURE_INSPECT | numbers | manual_fixture | registered_when_service_enabled |
| 251 | SD_READ | numbers_and_ascii | boot_read_only | registered_when_service_enabled |
| 252 | IR_REPLAY_LAST | numbers | manual_fixture | registered_when_service_enabled |
| 253 | IR_VERIFY_LAST | numbers | manual_fixture | registered_when_service_enabled |
| 260 | NEO_CAPS | numbers | boot_read_only | registered_when_service_enabled |
| 261 | NEO_IR_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 262 | NEO_IR_SCAN_START | numbers | manual_fixture | registered_when_service_enabled |
| 263 | NEO_IR_SCAN_STOP | numbers | manual_fixture | registered_when_service_enabled |
| 264 | NEO_IR_SCAN_READ | numbers | manual_fixture | registered_when_service_enabled |
| 265 | NEO_FILE_DOWNLOAD | numbers_and_ascii | manual_fixture | registered_when_service_enabled |
| 266 | NEO_FILE_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 267 | VM_DOWNLOAD | numbers_and_ascii | on_demand | registered_when_service_enabled |
| 268 | AUDIO_PLAY | numbers_and_ascii | manual_fixture | registered_when_service_enabled |
| 269 | NEO_DISPLAY_START | numbers_and_ascii | manual_fixture | registered_when_service_enabled |
| 270 | NEO_DISPLAY_STOP | numbers | manual_fixture | registered_when_service_enabled |
| 271 | NEO_DISPLAY_STATUS | numbers | boot_read_only | registered_when_service_enabled |
| 272 | NEO_IMAGE_FORMAT | numbers_and_ascii | manual_fixture | registered_when_service_enabled |
| 273 | NEO_OLED_DRAW | numbers_and_ascii | manual_fixture | registered_when_service_enabled |
| 274 | NEO_OLED_TEXT | numbers_and_ascii | manual_fixture | registered_when_service_enabled |

Full test assertions and recovery limits: [functions.json](config/functions.json).
Command framing/examples: [PROTOCOL.md](firmware/iris_noob/PROTOCOL.md).

Regenerate with `node iris/tools/update-function-catalog.mjs` from the repo root.
