# Noobia Model Context Protocol (MCP) Framework

This directory provides Noobia's unified Model Context Protocol (MCP) server
and client architecture, standardizing application-level tool discovery and execution
across Noobia inhabitants (Lynx, Iris, Rose, etc.) over Wi-Fi, Bluetooth, and local links.

## Background & Architecture

### 1. Transport & Wire Protocol (L1 - L4)
Noobia devices are accessed remotely over:
- **Wi-Fi** (TCP port `4243`): Lynx listens at `192.168.100.107:4243` with `AUTH/1` challenge-response framing. Iris uses `noob_tcp_server_transport.cpp`.
- **Bluetooth (BLE GATT)**: Iris connects as a BLE client to the Nexus GATT server bridge (`nexus_ble_bridge.sh`). Lynx exposes a GATT service with authenticated notifications (`lynx_ble_auth.py`).
- **Wire Protocol**: All transports communicate using the line-oriented `NRP/1` protocol (`NRP/1 <seq> <COMMAND> [args...]`).

### 2. Legacy DIY App-Level System
Previously, application-level tools were organized using custom, ad-hoc formats:
- In `lynx/tools/local_calls/` and `rose/calls/`, tools were declared as pairs of `<name>.json` (with custom `"protocol": "json-stdin"`, parameters schemas, and timeouts) and `<name>.sh` shell wrappers taking JSON on stdin.
- On Lynx, `lynx_noob_runtime.py` dynamically registered tools with an `nrp_id` into NRP/1.
- `lynx_agent.py` and `rose/chatbot/core.py` used proprietary `Catalog` and `Tools` classes that manually converted the `.json` files into OpenAI function-call schemas.
- External or modern AI agents (Antigravity, Claude Code, Cursor, Windsurf) had no standardized MCP access to device sensors and actuators.

### 3. The Standardized MCP System
The new MCP architecture standardizes everything at the application layer without breaking underlying hardware daemons or safety bounds:

```
┌─────────────────────────────────────────────────────────────┐
│             AI Agents (Antigravity, Claude, Codex)          │
└──────────────────────────────┬──────────────────────────────┘
                               │ JSON-RPC 2.0 (stdio)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Noobia MCP Server (noob_mcp.py)             │
│                                                             │
│  ├── Built-in Remote Tools (Lynx, Iris)                     │
│  ├── Dynamic Manifest Converter (manifest_converter.py)     │
│  └── Execution Router                                       │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
       NRP/1 over Wi-Fi/BT              Local Execution
               │                               │
               ▼                               ▼
    ┌──────────────────────┐         ┌────────────────────┐
    │  Lynx / Iris Device  │         │  Local Scripts     │
    │  Hardware Services   │         │  (json-stdin)      │
    └──────────────────────┘         └────────────────────┘
```

## Modules

- **[`noob_mcp.py`](file:///noobia/common/mcp/noob_mcp.py)**:
  The Model Context Protocol server. Fully implements JSON-RPC 2.0 methods:
  - `initialize`: handshake and server capabilities.
  - `tools/list`: enumerates all built-in and dynamic MCP tools.
  - `tools/call`: executes a tool and returns standard MCP content blocks.
  - Supports CLI inspection: `--list` and `--call <name> --args <json>`.

- **[`manifest_converter.py`](file:///noobia/common/mcp/manifest_converter.py)**:
  Translates legacy Noobia DIY `json-stdin` manifests (`.json`) into standard MCP tool schemas (`name`, `description`, `inputSchema`).

- **[`mcp_client.py`](file:///noobia/common/mcp/mcp_client.py)**:
  Standard Python client to query and invoke tools from any MCP server via subprocess stdio or in-process adapter (`InProcessMCPServerAdapter`).

- **[`test_noob_mcp.py`](file:///noobia/common/mcp/test_noob_mcp.py)**:
  Automated test suite verifying manifest conversion, JSON-RPC protocol compliance, tool invocation, and error handling.

## Available Tools

### Lynx Tools (over Wi-Fi `192.168.100.107:4243` / BT)
- `lynx_ping`: NRP/1 connectivity check.
- `lynx_status`: Full system status (battery, services, IP, thermal zones).
- `lynx_caps`: Registered capabilities and native functions.
- `lynx_battery`: Live battery capacity, temperature, voltage, and current.
- `lynx_camera_status`: Camera driver readiness and sensor binding status.
- `lynx_flashlight_pulse`: Bounded (20–100 ms) torch pulse with verification.
- `lynx_flashlight_stop`: Explicit light shutoff.
- `lynx_microphone_level`: 1-second RMS loudness capture without saving audio.
- `lynx_haptic_set`: 20–250 ms vibration motor pulse with cooldown.
- `lynx_haptic_stop`: Stop vibration motor.
- `lynx_motion_read`: 3-axis accelerometer vector.
- `lynx_magnetometer_read`: 3-axis AKM magnetometer vector.
- `lynx_light_read`: Ambient rear light reading.
- `lynx_proximity_read`: AMS proximity sensor reading.
- `lynx_queue_health`: Agent job queue health and status.
- `lynx_agent_health`: Local agent daemon health.
- `lynx_raw_nrp`: Execute an arbitrary bounded NRP/1 command.

### Iris Tools (over BLE / Wi-Fi / Serial)
- `iris_ping`: NRP/1 connectivity check.
- `iris_status`: Check BLE bridge and connection status.
- `iris_caps`: Enumerate Iris capabilities.
- `iris_camera_capture`: Trigger camera snapshot saved to SD card.
- `iris_storage_status`: Read micro-SD mount and storage status.
- `iris_mic_level`: Read microphone level.
- `iris_led_rgb`: Set RGB LED color.
- `iris_wifi_status`: Wi-Fi link status.
- `iris_time_now`: Monotonic millisecond counter.
- `iris_raw_nrp`: Execute an arbitrary bounded NRP/1 command.

## Configuration

### Antigravity (`~/.gemini/config/mcp_config.json`)
```json
{
  "mcpServers": {
    "noobia": {
      "command": "/usr/bin/python3",
      "args": ["/noobia/common/mcp/noob_mcp.py"],
      "disabled": false
    }
  }
}
```

### Claude Code (`~/.claude.json` / `claude mcp add`)
```sh
claude mcp add noobia -- /usr/bin/python3 /noobia/common/mcp/noob_mcp.py
```

## Running Tests

```sh
python3 -m unittest discover -s /noobia/common/mcp -p "test_*.py"
```
