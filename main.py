import sys
import time
from typing import Optional

import serial
from serial.tools import list_ports
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def command_to_bytes(command: str) -> bytes:
    replacements = {
        "\\r": "\r",
        "\\n": "\n",
        "\\t": "\t",
        "\\\\": "\\",
    }
    for text, control_char in replacements.items():
        command = command.replace(text, control_char)
    return command.encode("utf-8")


class SendWorker(QThread):
    cycle_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_normally = pyqtSignal()

    def __init__(
        self,
        port_name: str,
        baudrate: int,
        on_command: str,
        off_command: str,
        on_delay_ms: float,
        off_delay_ms: float,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self.port_name = port_name
        self.baudrate = baudrate
        self.on_command = on_command
        self.off_command = off_command
        self.on_delay_ms = on_delay_ms
        self.off_delay_ms = off_delay_ms
        self._stop_requested = False
        self._serial: Optional[serial.Serial] = None

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self.port_name,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
            )
            self.status_changed.emit(f"已连接 {self.port_name}")

            cycle = 0
            while not self._stop_requested:
                self._send_command(self.on_command)
                if self._wait_ms(self.on_delay_ms):
                    break

                self._send_command(self.off_command)
                cycle += 1
                self.cycle_changed.emit(cycle)
                if self._wait_ms(self.off_delay_ms):
                    break

            if self._stop_requested:
                self.status_changed.emit("已停止")
            else:
                self.finished_normally.emit()
        except serial.SerialException as exc:
            self.error_occurred.emit(f"串口错误：{exc}")
        except Exception as exc:
            self.error_occurred.emit(f"发送失败：{exc}")
        finally:
            if self._serial is not None and self._serial.is_open:
                self._serial.close()
            self._serial = None

    def _send_command(self, command: str) -> None:
        if self._serial is None or not self._serial.is_open:
            raise serial.SerialException("串口未打开")
        self._serial.write(command_to_bytes(command))
        self._serial.flush()
        self.status_changed.emit(f"已发送：{command}")

    def _wait_ms(self, milliseconds: float) -> bool:
        end_time = time.monotonic() + milliseconds / 1000
        while not self._stop_requested:
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                return False
            self.msleep(min(50, max(1, int(remaining * 1000))))
        return True


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: Optional[SendWorker] = None
        self.setWindowTitle("USB 转串口 ON/OFF 循环发送工具")
        self.setMinimumSize(560, 420)
        self._build_ui()
        self._refresh_ports()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        serial_group = QGroupBox("串口设置")
        serial_layout = QFormLayout(serial_group)
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self._refresh_ports)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_button)
        serial_layout.addRow("串口：", port_row)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baud_combo.setCurrentText("9600")
        serial_layout.addRow("波特率：", self.baud_combo)
        root_layout.addWidget(serial_group)

        command_group = QGroupBox("发送指令")
        command_layout = QFormLayout(command_group)
        self.on_command_edit = QLineEdit()
        self.on_command_edit.setText(":CONF:VOLT:DC\\r\\n")
        self.on_command_edit.setPlaceholderText("例如：:CONF:VOLT:DC\\r\\n")
        self.off_command_edit = QLineEdit()
        self.off_command_edit.setText(":CONF:VOLT:AC\\r\\n")
        self.off_command_edit.setPlaceholderText("例如：:CONF:VOLT:AC\\r\\n")
        command_layout.addRow("ON 指令：", self.on_command_edit)
        command_layout.addRow("OFF 指令：", self.off_command_edit)
        root_layout.addWidget(command_group)

        timing_group = QGroupBox("延时设置")
        timing_layout = QFormLayout(timing_group)
        self.on_delay_spin, self.on_delay_unit = self._create_delay_row()
        self.off_delay_spin, self.off_delay_unit = self._create_delay_row()
        timing_layout.addRow(
            "ON 后延时：", self._delay_row(self.on_delay_spin, self.on_delay_unit)
        )
        timing_layout.addRow(
            "OFF 后延时：", self._delay_row(self.off_delay_spin, self.off_delay_unit)
        )
        root_layout.addWidget(timing_group)

        control_layout = QHBoxLayout()
        self.start_button = QPushButton("启动")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self._start_sending)
        self.stop_button.clicked.connect(self._stop_sending)
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        root_layout.addLayout(control_layout)

        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("完成循环次数："))
        self.cycle_label = QLabel("0")
        self.cycle_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        status_layout.addWidget(self.cycle_label)
        status_layout.addStretch()
        self.status_label = QLabel("未启动")
        status_layout.addWidget(self.status_label)
        root_layout.addLayout(status_layout)
        root_layout.addStretch()

    @staticmethod
    def _create_delay_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 3600000)
        spin.setDecimals(3)
        spin.setSingleStep(100)
        spin.setValue(1000)
        return spin

    @classmethod
    def _create_delay_row(cls) -> tuple[QDoubleSpinBox, QComboBox]:
        spin = cls._create_delay_spin()
        unit = QComboBox()
        unit.addItem("毫秒", 1)
        unit.addItem("秒", 1000)
        unit.addItem("分钟", 60000)
        return spin, unit

    @staticmethod
    def _delay_row(spin: QDoubleSpinBox, unit: QComboBox) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(spin)
        layout.addWidget(unit)
        return row

    def _refresh_ports(self) -> None:
        current_port = self.port_combo.currentData()
        self.port_combo.clear()
        ports = list(list_ports.comports())
        for port in ports:
            self.port_combo.addItem(
                f"{port.device} - {port.description}",
                userData=port.device,
            )
        if not current_port:
            preferred_index = self.port_combo.findData("COM26")
            if preferred_index >= 0:
                self.port_combo.setCurrentIndex(preferred_index)
        if current_port:
            index = self.port_combo.findData(current_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        if not ports:
            self.port_combo.addItem("未发现串口", userData="")

    def _start_sending(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        port_name = self.port_combo.currentData()
        on_command = self.on_command_edit.text()
        off_command = self.off_command_edit.text()
        if not port_name:
            self._show_error("没有可用串口，请先连接 USB 转串口设备并点击刷新。")
            return
        if not on_command or not off_command:
            self._show_error("ON 指令和 OFF 指令都不能为空。")
            return

        self.cycle_label.setText("0")
        self.worker = SendWorker(
            port_name=port_name,
            baudrate=int(self.baud_combo.currentText()),
            on_command=on_command,
            off_command=off_command,
            on_delay_ms=self._delay_to_ms(self.on_delay_spin, self.on_delay_unit),
            off_delay_ms=self._delay_to_ms(self.off_delay_spin, self.off_delay_unit),
        )
        self.worker.cycle_changed.connect(
            lambda count: self.cycle_label.setText(str(count))
        )
        self.worker.status_changed.connect(self.status_label.setText)
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished_normally.connect(
            lambda: self.status_label.setText("循环已结束")
        )
        self._set_running_state(True)
        self.worker.start()

    def _stop_sending(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText("正在停止...")
            self.worker.stop()
            self.stop_button.setEnabled(False)

    def _on_worker_error(self, message: str) -> None:
        self.status_label.setText("发生错误")
        self._show_error(message)

    def _on_worker_finished(self) -> None:
        self._set_running_state(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.refresh_button.setEnabled(not running)
        self.port_combo.setEnabled(not running)
        self.baud_combo.setEnabled(not running)
        self.on_command_edit.setEnabled(not running)
        self.off_command_edit.setEnabled(not running)
        self.on_delay_spin.setEnabled(not running)
        self.off_delay_spin.setEnabled(not running)
        self.on_delay_unit.setEnabled(not running)
        self.off_delay_unit.setEnabled(not running)

    @staticmethod
    def _delay_to_ms(spin: QDoubleSpinBox, unit: QComboBox) -> float:
        return spin.value() * float(unit.currentData())

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "操作失败", message)

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
