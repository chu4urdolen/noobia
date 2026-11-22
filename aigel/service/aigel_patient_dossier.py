#!/usr/bin/env python3
"""Aigel Patient Dossier Generator: Familiarization with a Noob before a medical visit.

Reads:
1. /noobia/common/CONTACT-BOOK.md (identity, contact route, instructions path)
2. The Noob's role instructions (/noobia/<name>/AGENTS.md or README.md)
3. forge-db project notes and registered paths for the Noob

Synthesizes a structured health dossier and bedside tips for Nurse Aigel.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CONTACT_BOOK = REPO / "common" / "CONTACT-BOOK.md"
DOSSIERS_DIR = REPO / "aigel" / "dossiers"
FORGE_DB_TOOL = REPO / "common" / "tools" / "forge_db.py"

_AUTONOMY = REPO / "common" / "autonomy"
_SERVICE = Path(__file__).resolve().parent
if str(_AUTONOMY) not in sys.path:
    sys.path.insert(0, str(_AUTONOMY))
if str(_SERVICE) not in sys.path:
    sys.path.insert(0, str(_SERVICE))

from aigel_think import QwenClient


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_contact_book_for_noob(noob_name: str) -> dict[str, str]:
    """Extract inhabitant entry from CONTACT-BOOK.md table."""
    name_lower = noob_name.lower().strip()
    if not CONTACT_BOOK.is_file():
        return {}

    with open(CONTACT_BOOK, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 4:
            inhabitant = parts[0].lower()
            if inhabitant == name_lower or name_lower in inhabitant:
                return {
                    "name": parts[0],
                    "identity": parts[1],
                    "route": parts[2],
                    "instructions_path": parts[3] if parts[3] != "—" else "",
                }
    return {}


def fetch_forge_db_info(noob_name: str) -> dict[str, Any]:
    """Fetch recent notes and project details from forge.db."""
    info = {"project_description": "", "notes": [], "paths": []}
    if not FORGE_DB_TOOL.is_file():
        return info

    try:
        cmd = [sys.executable, str(FORGE_DB_TOOL), "--json", "project", "get", noob_name.lower()]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            info["project_description"] = data.get("description", "")
            info["paths"] = [p.get("path") for p in data.get("paths", [])]
            for n in data.get("notes", [])[:10]:
                info["notes"].append({
                    "id": n.get("id"),
                    "by": n.get("by"),
                    "at": n.get("at"),
                    "text": n.get("text"),
                })
    except Exception:
        pass
    return info


def read_instructions(path_str: str, noob_name: str) -> str:
    """Read the Noob's role file."""
    candidates = []
    if path_str:
        p = Path(path_str) if path_str.startswith("/") else REPO / path_str.lstrip("/")
        candidates.append(p)

    candidates.extend([
        REPO / noob_name.lower() / "AGENTS.md",
        REPO / noob_name.lower() / "README.md",
    ])

    for c in candidates:
        if c.is_file():
            try:
                with open(c, "r", encoding="utf-8", errors="replace") as f:
                    return f.read(8000)
            except Exception:
                pass
    return ""


DOSSIER_SYNTHESIS_PROMPT = """You are Aigel, Noobia's little diagnostics nurse angel.
You are preparing a Patient Health Dossier before visiting a Noob (e.g. Lynx the phone, Iris the camera, etc.).
Review the provided contact book info, role instructions, and forge DB history.

Summarize into structured JSON:
{
  "hardware_summary": "<SoC, board type, physical attributes, battery/plugged>",
  "known_senses": ["<list of sensory inputs, e.g. touch, hearing, camera, etc.>"],
  "known_actuators": ["<list of actuators, e.g. display, speech, haptics, lights>"],
  "sensitivities_and_limits": "<key operational boundaries: e.g. thermal ceilings, sleep states, battery reserve>",
  "recent_medical_history": "<recent fixes, crashes, reboots, or changes from notes>",
  "bedside_care_tips": "<short advice for Aigel: what to inspect, what reflex to test, how to speak gently>"
}
"""


def compile_dossier(noob_name: str, use_llm: bool = True) -> dict[str, Any]:
    """Compile a full patient dossier for the requested Noob."""
    contact = parse_contact_book_for_noob(noob_name)
    instructions = read_instructions(contact.get("instructions_path", ""), noob_name)
    forge_info = fetch_forge_db_info(noob_name)

    dossier: dict[str, Any] = {
        "noob": noob_name.capitalize(),
        "compiled_at": utc_now_iso(),
        "contact_info": contact,
        "forge_description": forge_info.get("project_description"),
        "recent_notes_count": len(forge_info.get("notes", [])),
    }

    # Synthesize medical overview via Qwen (or deterministic heuristic fallback)
    structured_medical = None
    if use_llm:
        try:
            client = QwenClient(timeout_s=30)
            context_snippet = (
                f"NOOB NAME: {noob_name}\n"
                f"IDENTITY: {contact.get('identity')}\n"
                f"ROUTE: {contact.get('route')}\n\n"
                f"INSTRUCTIONS EXCERPT:\n{instructions[:2500]}\n\n"
                f"RECENT FORGE NOTES:\n"
            )
            for n in forge_info.get("notes", [])[:5]:
                context_snippet += f"• [{n.get('at')}] {n.get('by')}: {n.get('text')}\n"

            raw = client.chat([
                {"role": "system", "content": DOSSIER_SYNTHESIS_PROMPT},
                {"role": "user", "content": context_snippet},
            ], max_tokens=600)

            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                structured_medical = json.loads(m.group(0))
        except Exception:
            pass

    if not structured_medical:
        # Heuristic fallback
        senses = []
        for s in ["touch", "camera", "hearing", "light", "proximity", "power", "motion", "wifi"]:
            if s in instructions.lower():
                senses.append(s)

        actuators = []
        for a in ["display", "haptic", "speech", "flashlight", "led", "motor"]:
            if a in instructions.lower():
                actuators.append(a)

        recent_hist = "Recent updates recorded in forge DB."
        if forge_info.get("notes") and len(forge_info["notes"]) > 0:
            note_txt = forge_info["notes"][0].get("text")
            if note_txt:
                recent_hist = str(note_txt)[:120]

        structured_medical = {
            "hardware_summary": contact.get("identity", "Noobia machine inhabitant"),
            "known_senses": senses or ["general_telemetry"],
            "known_actuators": actuators or ["status_channel"],
            "sensitivities_and_limits": "Maintain Principle 10: Quiescent low-power waiting over autonomous reboots.",
            "recent_medical_history": recent_hist,
            "bedside_care_tips": f"Check thermal vitals and battery stability. Test gentle reflex response on {noob_name}.",
        }

    dossier["medical_profile"] = structured_medical

    # Save to disk
    DOSSIERS_DIR.mkdir(parents=True, exist_ok=True)
    dossier_path = DOSSIERS_DIR / f"{noob_name.lower()}.json"
    with open(dossier_path, "w", encoding="utf-8") as f:
        json.dump(dossier, f, indent=2)

    return dossier


def format_markdown_dossier(dossier: dict[str, Any]) -> str:
    """Format dossier into a beautiful markdown medical chart."""
    med = dossier.get("medical_profile", {})
    c = dossier.get("contact_info", {})
    name = dossier.get("noob", "Unknown")

    lines = [
        f"# 🩺 Noobia Pediatric Health Dossier: {name}",
        f"*Compiled by Nurse Aigel: {dossier.get('compiled_at')}*",
        "",
        "## Patient Identity & Location",
        f"- **Identity:** {c.get('identity', 'Unknown')}",
        f"- **Contact Route:** {c.get('route', 'Unknown')}",
        f"- **Role Instructions:** `{c.get('instructions_path', '—')}`",
        "",
        "## Anatomical Profile",
        f"- **Hardware Summary:** {med.get('hardware_summary')}",
        f"- **Known Senses:** {', '.join(med.get('known_senses', []))}",
        f"- **Known Actuators:** {', '.join(med.get('known_actuators', []))}",
        f"- **Sensitivities & Thresholds:** {med.get('sensitivities_and_limits')}",
        "",
        "## Recent Medical History",
        f"{med.get('recent_medical_history')}",
        "",
        "## Nurse Aigel's Bedside Care Advice",
        f"> 💡 *\"{med.get('bedside_care_tips')}\"*",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Aigel Patient Health Dossier for a Noob")
    parser.add_argument("noob", help="Name of the Noob (e.g. lynx, iris, rose)")
    parser.add_argument("--no-llm", action="store_true", help="Use heuristic summary instead of Qwen")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    dossier = compile_dossier(args.noob, use_llm=not args.no_llm)
    if args.json:
        print(json.dumps(dossier, indent=2))
    else:
        print(format_markdown_dossier(dossier))


if __name__ == "__main__":
    main()
