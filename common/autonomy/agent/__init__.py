"""Common autonomy agent subsystem for all Noobs (NA-81, NA-82).

Provides universal building blocks:
- JobQueue: durable filesystem queue with HMAC verification.
- ToolBroker: privileged isolation daemon validating tools and arguments.
- Worker: background loop claiming jobs, enforcing inference gates, and acks.
- Injection: prompt injection inspection and message sanitization.
- Agent: universal SENSE and CHAT loop driven by profile.
"""

from .jobqueue import JobQueue, QueueError
from .injection import scrub, inspect, check_message
from .broker import ToolBroker, manifest, validate_args, dispatch_tool
from .health import agent_health
from .coder_tool import ask_coder

__all__ = [
    "JobQueue",
    "QueueError",
    "scrub",
    "inspect",
    "check_message",
    "ToolBroker",
    "manifest",
    "validate_args",
    "dispatch_tool",
    "agent_health",
    "ask_coder",
]
