# -*- coding: utf-8 -*-
"""Offline / credential gate for P6 AI entry points.

ALL AI UI must be disabled when there is no API key or no network.
Deterministic engines (fill / aggregate / verify / booklet) stay usable.

Credentials: DEEPSEEK_API_KEY env only. Never read a key from disk/config.
Live model replies are never invented: no key → unavailable, not a fake answer.
"""
from __future__ import annotations

import os
import socket
from typing import Optional
from urllib.parse import urlparse

DEFAULT_API = 'https://api.deepseek.com'
PROBE_HOST = 'api.deepseek.com'
PROBE_PORT = 443


class AiUnavailable(RuntimeError):
    """Raised when an AI call is attempted while the gate is closed."""

    def __init__(self, reason: str, status: Optional[dict] = None):
        super().__init__(reason)
        self.reason = reason
        self.status = status or {}


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name) or '').strip().lower() in (
        '1', 'true', 'yes', 'on', 'offline',
    )


def api_key() -> str:
    return str(os.environ.get('DEEPSEEK_API_KEY') or '').strip()


def api_base() -> str:
    return (os.environ.get('DEEPSEEK_BASE_URL') or DEFAULT_API).rstrip('/')


def _probe_host_port(url: str, timeout: float = 1.5) -> tuple[bool, str]:
    host, port = PROBE_HOST, PROBE_PORT
    try:
        parsed = urlparse(url if '://' in url else 'https://' + url)
        host = parsed.hostname or host
        port = parsed.port or (443 if (parsed.scheme or 'https') == 'https' else 80)
    except ValueError:
        pass
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True, 'ok'
    except OSError as e:
        return False, str(e)


def ai_status(probe_network: bool = True) -> dict:
    """Return a JSON-serialisable gate status. Never claims a live model ran."""
    force_off = _env_flag('YANSHOU_AI_OFFLINE')
    key = api_key()
    has_key = bool(key)
    network = None
    net_detail = ''
    if force_off:
        available = False
        reason = 'offline-flag'
    elif not has_key:
        available = False
        reason = 'no-api-key'
    else:
        if probe_network and not _env_flag('YANSHOU_AI_SKIP_NET'):
            network, net_detail = _probe_host_port(api_base())
            if not network:
                available = False
                reason = 'no-network'
            else:
                available = True
                reason = 'ready'
        else:
            available = True
            reason = 'ready-key-only'
            network = None
    return {
        'available': available,
        'reason': reason,
        'hasKey': has_key,
        'network': network,
        'networkDetail': net_detail,
        'apiBase': api_base(),
        'model': os.environ.get('YANSHOU_AI_MODEL') or 'deepseek-flash',
        'liveModel': False,  # status check never calls the model
        'offlineFlag': force_off,
    }


def require_ai(status: Optional[dict] = None) -> dict:
    st = status or ai_status()
    if not st.get('available'):
        raise AiUnavailable(
            'AI 不可用（%s）。断网或无 DEEPSEEK_API_KEY 时入口应置灰。' % st.get('reason'),
            st)
    return st
