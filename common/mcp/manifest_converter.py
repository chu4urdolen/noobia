#!/usr/bin/env python3
"""Convert Noobia DIY json-stdin tool manifests into standard MCP tool schemas."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple

NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


def manifest_to_mcp_tool(name: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a single Noobia tool manifest dict into an MCP Tool specification.

    Args:
        name: Name of the tool.
        meta: The raw dict loaded from the .json manifest file.

    Returns:
        Standard MCP tool dictionary with name, description, and inputSchema.

    Raises:
        ValueError: If the manifest does not match the expected DIY schema.
    """
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise ValueError(f"Invalid tool name: {name}")

    if not isinstance(meta, dict):
        raise ValueError(f"Manifest for {name} must be a dictionary")

    protocol = meta.get("protocol")
    if protocol not in ("json-stdin", "command-stdin", "argv"):
        raise ValueError(f"Unsupported manifest protocol '{protocol}' for {name}")

    description = meta.get("description", f"Noobia tool: {name}")
    if not isinstance(description, str) or not description.strip():
        description = f"Noobia tool: {name}"

    parameters = meta.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    # Ensure valid JSON schema structure for inputSchema
    schema = {
        "type": "object",
        "properties": parameters.get("properties", {}),
    }
    if "required" in parameters:
        schema["required"] = list(parameters["required"])
    if "additionalProperties" in parameters:
        schema["additionalProperties"] = parameters["additionalProperties"]

    return {
        "name": name,
        "description": description.strip(),
        "inputSchema": schema,
    }


def load_manifest_tools(
    directory: str | Path,
) -> Dict[str, Tuple[Path, Dict[str, Any], Dict[str, Any]]]:
    """Scan a directory for Noobia tool manifests and convert them to MCP tools.

    Looks for pairs of `<name>.json` and `<name>.sh`.

    Returns:
        Dict mapping tool_name -> (script_path, raw_meta, mcp_tool_def)
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return {}

    tools: Dict[str, Tuple[Path, Dict[str, Any], Dict[str, Any]]] = {}
    for manifest_path in sorted(dir_path.glob("*.json")):
        name = manifest_path.stem
        if not NAME_PATTERN.match(name):
            continue

        script_path = manifest_path.with_suffix(".sh")
        if script_path.is_symlink() or not script_path.is_file():
            # Script might be absent if this is pure metadata or remote descriptor
            script_path = None

        try:
            raw_meta = json.loads(manifest_path.read_text(encoding="utf-8"))
            mcp_tool = manifest_to_mcp_tool(name, raw_meta)
            tools[name] = (script_path, raw_meta, mcp_tool)
        except Exception:
            # Skip malformed or incompatible files gracefully
            continue

    return tools
