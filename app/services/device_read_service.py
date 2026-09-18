import time
from collections.abc import Callable

import serial

from app.models import DeviceReadMode, DeviceReadResult, DeviceVerificationConfig
from app.utils import command_to_bytes


def read_device(
    config: DeviceVerificationConfig,
    timeout_ms: float,
    should_stop: Callable[[], bool] | None = None,
    serial_factory: Callable[..., serial.Serial] = serial.Serial,
) -> DeviceReadResult:
    """Execute one device read operation without touching UI state."""
    serial_connection: serial.Serial | None = None
    query_sent = False
    transmitted = b""
    try:
        serial_connection = serial_factory(
            port=config.port_name,
            baudrate=config.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
        )
        if config.mode is DeviceReadMode.SEND_AND_READ:
            serial_connection.reset_input_buffer()
            transmitted = command_to_bytes(config.command)
            serial_connection.write(transmitted)
            serial_connection.flush()
            query_sent = True

        deadline = time.monotonic() + max(0, timeout_ms) / 1000
        response = bytearray()
        while time.monotonic() < deadline:
            if should_stop is not None and should_stop():
                return DeviceReadResult(
                    transmitted=transmitted,
                    response=bytes(response),
                    status="cancelled",
                    query_sent=query_sent,
                )

            waiting = serial_connection.in_waiting
            if waiting:
                response.extend(serial_connection.read(waiting))
                if response.endswith((b"\n", b"\r")):
                    break
            time.sleep(0.02)

        if not response:
            return DeviceReadResult(
                transmitted=transmitted,
                response=b"",
                status="timeout",
                query_sent=query_sent,
            )

        text = bytes(response).decode("utf-8", errors="replace").strip()
        if not config.model_keyword:
            status = "unjudged"
        else:
            status = "pass" if config.model_keyword in text else "fail"
        return DeviceReadResult(
            transmitted=transmitted,
            response=bytes(response),
            status=status,
            query_sent=query_sent,
        )
    except serial.SerialException as exc:
        return DeviceReadResult(
            transmitted=transmitted,
            response=b"",
            status="error",
            query_sent=query_sent,
            error_message=f"设备串口错误：{exc}",
        )
    except Exception as exc:
        return DeviceReadResult(
            transmitted=transmitted,
            response=b"",
            status="error",
            query_sent=query_sent,
            error_message=f"设备回读失败：{exc}",
        )
    finally:
        if serial_connection is not None and serial_connection.is_open:
            serial_connection.close()
