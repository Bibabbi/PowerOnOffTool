from dataclasses import dataclass
from enum import Enum


class DeviceReadMode(str, Enum):
    SEND_AND_READ = "send_and_read"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class DeviceVerificationConfig:
    port_name: str
    baudrate: int
    command: str
    model_keyword: str
    mode: DeviceReadMode
    read_delay_ms: float
    read_timeout_ms: float


@dataclass(frozen=True)
class DeviceReadResult:
    transmitted: bytes
    response: bytes
    status: str
    query_sent: bool
    error_message: str = ""
