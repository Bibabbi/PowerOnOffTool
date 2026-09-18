import time
from typing import Optional

import serial
from PyQt6.QtCore import QThread, pyqtSignal

from app.models import DeviceReadResult, DeviceVerificationConfig
from app.services.device_read_service import read_device
from app.utils import command_to_bytes


class SendWorker(QThread):
    cycle_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    command_sent = pyqtSignal()
    device_verification_started = pyqtSignal()
    device_verification_finished = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    finished_normally = pyqtSignal()

    def __init__(
        self,
        serial_connection: serial.Serial,
        on_command: str,
        off_command: str,
        on_delay_ms: float,
        off_delay_ms: float,
        cycle_count: int,
        device_config: DeviceVerificationConfig | None = None,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self._serial = serial_connection
        self.on_command = on_command
        self.off_command = off_command
        self.on_delay_ms = on_delay_ms
        self.off_delay_ms = off_delay_ms
        self.cycle_count = cycle_count
        self.device_config = device_config
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            if not self._serial.is_open:
                raise serial.SerialException("串口未打开")
            self.status_changed.emit(f"已连接 {self._serial.port}")

            cycle = 0
            while not self._stop_requested:
                self._send_command(self.on_command)
                on_deadline = time.monotonic() + self.on_delay_ms / 1000

                if self.device_config is not None:
                    if self._wait_until(
                        min(
                            on_deadline,
                            time.monotonic()
                            + self.device_config.read_delay_ms / 1000,
                        )
                    ):
                        self._send_protection_off()
                        break

                    remaining_ms = max(0, (on_deadline - time.monotonic()) * 1000)
                    self.device_verification_started.emit()
                    result = read_device(
                        self.device_config,
                        remaining_ms,
                        should_stop=lambda: self._stop_requested,
                    )
                    self.device_verification_finished.emit(result)
                    if self._stop_requested:
                        self._send_protection_off()
                        break

                if self._wait_until(on_deadline):
                    self._send_protection_off()
                    break

                self._send_command(self.off_command)
                cycle += 1
                self.cycle_changed.emit(cycle)
                if cycle >= self.cycle_count:
                    self.finished_normally.emit()
                    return
                if self._wait_ms(self.off_delay_ms):
                    break

            if self._stop_requested:
                self.status_changed.emit("已停止")
        except serial.SerialException as exc:
            self.error_occurred.emit(f"串口错误：{exc}")
        except Exception as exc:
            self.error_occurred.emit(f"发送失败：{exc}")

    def _send_command(self, command: str) -> None:
        if self._serial is None or not self._serial.is_open:
            raise serial.SerialException("串口未打开")
        self._serial.write(command_to_bytes(command))
        self._serial.flush()
        self.command_sent.emit()
        self.status_changed.emit(f"已发送：{command}")

    def _wait_ms(self, milliseconds: float) -> bool:
        return self._wait_until(time.monotonic() + milliseconds / 1000)

    def _wait_until(self, deadline: float) -> bool:
        while not self._stop_requested:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self.msleep(min(50, max(1, int(remaining * 1000))))
        return True

    def _send_protection_off(self) -> None:
        try:
            self._send_command(self.off_command)
            self.status_changed.emit("已发送保护 OFF 指令")
        except Exception as exc:
            self.error_occurred.emit(f"保护 OFF 指令发送失败：{exc}")
