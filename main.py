import sys
import time
from typing import Optional

import serial
from serial.tools import list_ports
from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


BAUDRATES = ["9600", "19200", "38400", "57600", "115200"]


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


class DeviceReadWorker(QThread):
    response_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    finished_reading = pyqtSignal()

    def __init__(
        self,
        port_name: str,
        baudrate: int,
        command: str,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self.port_name = port_name
        self.baudrate = baudrate
        self.command = command
        self._serial: Optional[serial.Serial] = None

    def run(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self.port_name,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            self._serial.reset_input_buffer()
            self._serial.write(command_to_bytes(self.command))
            self._serial.flush()

            deadline = time.monotonic() + 2.0
            response = bytearray()
            while time.monotonic() < deadline:
                waiting = self._serial.in_waiting
                if waiting:
                    response.extend(self._serial.read(waiting))
                    if response.endswith(b"\n") or response.endswith(b"\r"):
                        break
                time.sleep(0.02)

            self.response_received.emit(bytes(response))
        except serial.SerialException as exc:
            self.error_occurred.emit(f"设备串口错误：{exc}")
        except Exception as exc:
            self.error_occurred.emit(f"设备回读失败：{exc}")
        finally:
            if self._serial is not None and self._serial.is_open:
                self._serial.close()
            self._serial = None
            self.finished_reading.emit()


class PowerControlPanel(QGroupBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("电源控制", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self._create_serial_group())
        layout.addWidget(self._create_command_group())
        layout.addWidget(self._create_timing_group())
        layout.addLayout(self._create_control_row())
        layout.addLayout(self._create_status_row())
        layout.addLayout(self._create_elapsed_row())
        layout.addStretch()

    def _create_serial_group(self) -> QGroupBox:
        group = QGroupBox("串口设置")
        form = QFormLayout(group)

        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("刷新")
        port_row = QHBoxLayout()
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_button)
        form.addRow("串口：", port_row)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems(BAUDRATES)
        self.baud_combo.setCurrentText("9600")
        form.addRow("波特率：", self.baud_combo)
        return group

    def _create_command_group(self) -> QGroupBox:
        group = QGroupBox("发送指令")
        form = QFormLayout(group)

        self.on_command_edit = QLineEdit(":CONF:VOLT:DC\\r\\n")
        self.on_command_edit.setPlaceholderText(
            "输入示例：ON 或 :CONF:VOLT:DC\\r\\n"
        )
        self.off_command_edit = QLineEdit(":CONF:VOLT:AC\\r\\n")
        self.off_command_edit.setPlaceholderText(
            "输入示例：OFF 或 :CONF:VOLT:AC\\r\\n"
        )
        form.addRow("ON 指令：", self.on_command_edit)
        form.addRow("OFF 指令：", self.off_command_edit)
        return group

    def _create_timing_group(self) -> QGroupBox:
        group = QGroupBox("延时设置")
        form = QFormLayout(group)
        self.on_delay_spin, self.on_delay_unit = self._create_delay_controls()
        self.off_delay_spin, self.off_delay_unit = self._create_delay_controls()
        form.addRow(
            "ON 后延时：", self._delay_row(self.on_delay_spin, self.on_delay_unit)
        )
        form.addRow(
            "OFF 后延时：", self._delay_row(self.off_delay_spin, self.off_delay_unit)
        )
        return group

    def _create_control_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.start_button = QPushButton("启动")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        return layout

    def _create_status_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel("完成循环次数："))
        self.cycle_label = QLabel("0")
        self.cycle_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self.cycle_label)
        layout.addStretch()
        self.status_label = QLabel("未启动")
        layout.addWidget(self.status_label)
        return layout

    def _create_elapsed_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel("已执行时间："))
        self.elapsed_label = QLabel("00:00:00")
        self.elapsed_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.elapsed_label)
        layout.addStretch()
        return layout

    @staticmethod
    def _create_delay_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 3600000)
        spin.setDecimals(3)
        spin.setSingleStep(100)
        spin.setValue(1000)
        return spin

    @classmethod
    def _create_delay_controls(cls) -> tuple[QDoubleSpinBox, QComboBox]:
        spin = cls._create_delay_spin()
        unit = QComboBox()
        unit.addItem("ms", 1)
        unit.addItem("s", 1000)
        unit.addItem("min", 60000)
        return spin, unit

    @staticmethod
    def _delay_row(spin: QDoubleSpinBox, unit: QComboBox) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(spin)
        layout.addWidget(unit)
        return row

    def set_running_state(self, running: bool) -> None:
        enabled = not running
        for widget in (
            self.refresh_button,
            self.port_combo,
            self.baud_combo,
            self.on_command_edit,
            self.off_command_edit,
            self.on_delay_spin,
            self.off_delay_spin,
            self.on_delay_unit,
            self.off_delay_unit,
        ):
            widget.setEnabled(enabled)
        self.start_button.setEnabled(enabled)
        self.stop_button.setEnabled(running)


class DeviceControlPanel(QGroupBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("设备端控制", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.enable_checkbox = QCheckBox("启用设备端控制")
        layout.addWidget(self.enable_checkbox)
        layout.addWidget(self._create_device_settings_group())
        layout.addWidget(self._create_command_check_group())
        layout.addWidget(self._create_status_group())
        layout.addWidget(self._create_readback_group(), 1)
        layout.addStretch()
        self.enable_checkbox.toggled.connect(self.set_enabled)
        self.set_enabled(False)

    def _create_device_settings_group(self) -> QGroupBox:
        group = QGroupBox("设备设置")
        form = QFormLayout(group)

        self.device_port_combo = QComboBox()
        self.device_refresh_button = QPushButton("刷新")
        port_row = QHBoxLayout()
        port_row.addWidget(self.device_port_combo, 1)
        port_row.addWidget(self.device_refresh_button)
        form.addRow("串口：", port_row)

        self.device_baud_combo = QComboBox()
        self.device_baud_combo.addItems(BAUDRATES)
        self.device_baud_combo.setCurrentText("9600")
        form.addRow("波特率：", self.device_baud_combo)
        return group

    def _create_command_check_group(self) -> QGroupBox:
        group = QGroupBox("指令判断")
        form = QFormLayout(group)
        self.device_command_edit = QLineEdit()
        self.device_command_edit.setPlaceholderText("输入示例：*IDN?\\r\\n")
        self.device_model_edit = QLineEdit()
        self.device_read_button = QPushButton("发送并回读")
        self.device_model_edit.setPlaceholderText(
            "输入示例：MODEL-123 或设备型号关键字"
        )
        form.addRow("发送指令：", self.device_command_edit)
        form.addRow("回读判断型号：", self.device_model_edit)
        form.addRow("", self.device_read_button)
        return group

    def _create_status_group(self) -> QGroupBox:
        group = QGroupBox("设备状态")
        form = QFormLayout(group)
        self.connection_label = QLabel("未连接")
        self.test_count_label = QLabel("0")
        self.last_action_label = QLabel("无")
        form.addRow("连接状态：", self.connection_label)
        form.addRow("测试次数：", self.test_count_label)
        form.addRow("最近操作：", self.last_action_label)
        return group

    def _create_readback_group(self) -> QGroupBox:
        group = QGroupBox("设备回读信息")
        layout = QVBoxLayout(group)
        self.readback_output = QPlainTextEdit()
        self.readback_output.setReadOnly(True)
        self.readback_output.setPlaceholderText("设备返回的信息将在这里显示")
        layout.addWidget(self.readback_output)
        return group

    def set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.device_port_combo,
            self.device_refresh_button,
            self.device_baud_combo,
            self.device_command_edit,
            self.device_model_edit,
            self.device_read_button,
        ):
            widget.setEnabled(enabled)

    def refresh_ports(self) -> None:
        current_port = self.device_port_combo.currentData()
        self.device_port_combo.clear()
        ports = list(list_ports.comports())
        for port in ports:
            self.device_port_combo.addItem(
                f"{port.device} - {port.description}",
                userData=port.device,
            )
        if current_port:
            index = self.device_port_combo.findData(current_port)
            if index >= 0:
                self.device_port_combo.setCurrentIndex(index)
        if not ports:
            self.device_port_combo.addItem("未发现串口", userData="")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: Optional[SendWorker] = None
        self.device_read_worker: Optional[DeviceReadWorker] = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_elapsed_time)
        self.elapsed_start_time: Optional[float] = None
        self.setWindowTitle("USB 转串口 ON/OFF 循环发送工具")
        self.setMinimumSize(980, 520)
        self._build_ui()
        self._bind_aliases()
        self._connect_signals()
        self._refresh_ports()
        self.device_panel.refresh_ports()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)
        self.power_panel = PowerControlPanel()
        self.device_panel = DeviceControlPanel()
        layout.addWidget(self.power_panel, 3)
        layout.addWidget(self.device_panel, 2)

    def _bind_aliases(self) -> None:
        self.port_combo = self.power_panel.port_combo
        self.refresh_button = self.power_panel.refresh_button
        self.baud_combo = self.power_panel.baud_combo
        self.on_command_edit = self.power_panel.on_command_edit
        self.off_command_edit = self.power_panel.off_command_edit
        self.on_delay_spin = self.power_panel.on_delay_spin
        self.on_delay_unit = self.power_panel.on_delay_unit
        self.off_delay_spin = self.power_panel.off_delay_spin
        self.off_delay_unit = self.power_panel.off_delay_unit
        self.start_button = self.power_panel.start_button
        self.stop_button = self.power_panel.stop_button
        self.cycle_label = self.power_panel.cycle_label
        self.status_label = self.power_panel.status_label
        self.elapsed_label = self.power_panel.elapsed_label

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self._refresh_ports)
        self.device_panel.device_refresh_button.clicked.connect(
            self.device_panel.refresh_ports
        )
        self.device_panel.device_read_button.clicked.connect(
            self._read_device_response
        )
        self.start_button.clicked.connect(self._start_sending)
        self.stop_button.clicked.connect(self._stop_sending)

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
            index = self.port_combo.findData("COM26")
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        if current_port:
            index = self.port_combo.findData(current_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        if not ports:
            self.port_combo.addItem("未发现串口", userData="")

    def _read_device_response(self) -> None:
        if self.device_read_worker is not None and self.device_read_worker.isRunning():
            return

        port_name = self.device_panel.device_port_combo.currentData()
        command = self.device_panel.device_command_edit.text()
        if not port_name:
            self._show_error("没有可用的设备串口，请先刷新并选择串口。")
            return
        if not command:
            self._show_error("设备发送指令不能为空。")
            return

        self.device_panel.readback_output.clear()
        self.device_panel.readback_output.setPlainText("正在发送并等待设备回读...")
        self.device_panel.connection_label.setText("读取中")
        self.device_panel.last_action_label.setText("发送并回读")
        self.device_panel.device_read_button.setEnabled(False)
        self.device_read_worker = DeviceReadWorker(
            port_name=port_name,
            baudrate=int(self.device_panel.device_baud_combo.currentText()),
            command=command,
        )
        self.device_read_worker.response_received.connect(
            self._show_device_response
        )
        self.device_read_worker.error_occurred.connect(self._on_device_read_error)
        self.device_read_worker.finished_reading.connect(
            self._on_device_read_finished
        )
        self.device_read_worker.start()

    def _show_device_response(self, response: bytes) -> None:
        if not response:
            self.device_panel.readback_output.setPlainText(
                "未读取到设备返回信息（超时）。"
            )
            self.device_panel.connection_label.setText("无返回")
            return

        text = response.decode("utf-8", errors="replace").strip()
        keyword = self.device_panel.device_model_edit.text().strip()
        result = "未判断"
        if keyword:
            result = "PASS" if keyword in text else "FAIL"
        self.device_panel.readback_output.setPlainText(
            f"原始文本：\n{text}\n\n"
            f"十六进制：\n{response.hex(' ')}\n\n"
            f"型号判断：{result}"
        )
        self.device_panel.connection_label.setText("已完成")
        self.device_panel.test_count_label.setText(
            str(int(self.device_panel.test_count_label.text()) + 1)
        )

    def _on_device_read_error(self, message: str) -> None:
        self.device_panel.readback_output.setPlainText(message)
        self.device_panel.connection_label.setText("错误")

    def _on_device_read_finished(self) -> None:
        self.device_panel.device_read_button.setEnabled(
            self.device_panel.enable_checkbox.isChecked()
        )
        if self.device_read_worker is not None:
            self.device_read_worker.deleteLater()
            self.device_read_worker = None

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
        self.elapsed_start_time = time.monotonic()
        self.elapsed_label.setText("00:00:00")
        self.elapsed_timer.start()
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
        self._update_elapsed_time()
        self.elapsed_timer.stop()
        self._set_running_state(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _set_running_state(self, running: bool) -> None:
        self.power_panel.set_running_state(running)

    def _update_elapsed_time(self) -> None:
        if self.elapsed_start_time is None:
            return
        elapsed_seconds = max(0, int(time.monotonic() - self.elapsed_start_time))
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.elapsed_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    @staticmethod
    def _delay_to_ms(spin: QDoubleSpinBox, unit: QComboBox) -> float:
        return spin.value() * float(unit.currentData())

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "操作失败", message)

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        if (
            self.device_read_worker is not None
            and self.device_read_worker.isRunning()
        ):
            self.device_read_worker.wait(2500)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
