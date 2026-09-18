from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from app.models import DeviceReadResult, DeviceVerificationConfig
from app.services.device_read_service import read_device


class DeviceReadWorker(QThread):
    result_received = pyqtSignal(object)
    finished_reading = pyqtSignal()

    def __init__(
        self,
        config: DeviceVerificationConfig,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config

    def run(self) -> None:
        try:
            result = read_device(self.config, self.config.read_timeout_ms)
            self.result_received.emit(result)
        except Exception as exc:
            self.result_received.emit(
                DeviceReadResult(
                    transmitted=b"",
                    response=b"",
                    status="error",
                    query_sent=False,
                    error_message=f"设备回读失败：{exc}",
                )
            )
        finally:
            self.finished_reading.emit()
