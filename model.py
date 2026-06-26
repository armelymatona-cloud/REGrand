# models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Account:
    id: int
    phone: str
    session_string: str
    api_id: int
    api_hash: str
    proxy: Optional[str]
    is_active: bool
    created_at: str
    last_used: Optional[str]

@dataclass
class Proxy:
    id: int
    address: str
    port: int
    username: Optional[str]
    password: Optional[str]
    protocol: str  # socks5, http
    is_active: bool
    last_checked: Optional[str]

@dataclass
class Target:
    id: int
    target_id: str
    reports_count: int
    last_reported: Optional[str]
    created_at: str