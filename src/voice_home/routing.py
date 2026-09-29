"""Only the provisioned number can become an outgoing destination."""

import re
from .config import Caller, number


def identify(remote_uri: str, source: str, host: str, callers: list[Caller], region="DE") -> Caller | None:
    if source.rsplit(":", 1)[0] != host:
        return None
    # PJSIP's canonical From URI may contain a quoted display name.
    uri = remote_uri.rsplit("<", 1)[-1].rstrip(">")
    match = re.fullmatch(r"sips?:([+0-9]+)@[^\s<>]+", uri)
    if not match:
        return None
    try:
        identity = number(match.group(1), region)
    except ValueError:
        return None
    return next((c for c in callers if c.number == identity), None)


def callback_uri(caller: Caller, host: str, port: int, transport="udp") -> str:
    suffix = ";transport=tcp" if transport == "tcp" else ""
    return f"sip:{caller.number}@{host}:{port}{suffix}"
