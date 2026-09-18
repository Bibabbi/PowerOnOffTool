import time
from typing import Optional

import serial
from serial.tools import list_ports
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from app.models import DeviceReadMode, DeviceReadResult, DeviceVerificationConfig
from app.widgets.device_control_panel import DeviceControlPanel
from app.widgets.power_control_panel import PowerControlPanel
from app.workers.device_read_worker import DeviceReadWorker
from app.workers.power_worker import SendWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: Optional[SendWorker] = None
        self.device_read_worker: Optional[DeviceReadWorker] = None
        self.power_serial: Optional[serial.Serial] = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_elapsed_time)
        self.elapsed_start_time: Optional[float] = None
        self.setWindowTitle("USB 转串口 ON/OFF 循环发送工具")
        self.setMinimumSize(1080, 720)
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
        self.cycle_count_spin = self.power_panel.cycle_count_spin
        self.start_button = self.power_panel.start_button
        self.stop_button = self.power_panel.stop_button
        self.cycle_label = self.power_panel.cycle_label
        self.status_label = self.power_panel.status_label
        self.elapsed_label = self.power_panel.elapsed_label

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self._refresh_ports)
        self.power_panel.connection_button.clicked.connect(
            self._toggle_power_connection
        )
        self.port_combo.currentIndexChanged.connect(
            self._on_power_connection_settings_changed
        )
        self.baud_combo.currentTextChanged.connect(
            self._on_power_connection_settings_changed
        )
        self.device_panel.device_refresh_button.clicked.connect(
            self.device_panel.refresh_ports
        )
        self.device_panel.device_read_button.clicked.connect(
            lambda: self._read_device_response(DeviceReadMode.SEND_AND_READ)
        )
        self.device_panel.device_read_only_button.clicked.connect(
            lambda: self._read_device_response(DeviceReadMode.READ_ONLY)
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

    def _toggle_power_connection(self) -> None:
        if self.power_serial is not None and self.power_serial.is_open:
            self._disconnect_power_serial()
            return

        port_name = self.port_combo.currentData()
        if not port_name:
            self.power_panel.set_connection_status(False)
            self._show_error("没有可用串口，请先连接 USB 转串口设备并点击刷新。")
            return

        try:
            self.power_serial = serial.Serial(
                port=port_name,
                baudrate=int(self.baud_combo.currentText()),
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
            )
        except serial.SerialException as exc:
            self.power_serial = None
            self.power_panel.set_connection_status(False)
            self._show_error(f"串口连接失败：{exc}")
            return

        self.power_panel.set_connection_status(True)
        self.status_label.setText(f"已连接 {port_name}")

    def _disconnect_power_serial(self) -> None:
        if self.power_serial is not None and self.power_serial.is_open:
            self.power_serial.close()
        self.power_serial = None
        self.power_panel.set_connection_status(None)
        self.status_label.setText("未启动")

    def _on_power_connection_settings_changed(self) -> None:
        if self.power_serial is not None:
            self._disconnect_power_serial()

    def _read_device_response(self, mode: DeviceReadMode) -> None:
        if self.device_read_worker is not None and self.device_read_worker.isRunning():
            return

        config = self.device_panel.build_config(mode)
        if not config.port_name:
            self._show_error("没有可用的设备串口，请先刷新并选择串口。")
            return
        if mode is DeviceReadMode.SEND_AND_READ and not config.command:
            self._show_error("设备发送指令不能为空。")
            return

        self.device_panel.set_reading_state(mode)
        self.device_panel.device_read_button.setEnabled(False)
        self.device_panel.device_read_only_button.setEnabled(False)
        self.device_read_worker = DeviceReadWorker(config)
        self.device_read_worker.result_received.connect(self._show_device_result)
        self.device_read_worker.finished_reading.connect(
            self._on_device_read_finished
        )
        self.device_read_worker.start()

    def _show_device_result(self, result: DeviceReadResult) -> None:
        self.device_panel.show_result(result)

    def _on_device_read_finished(self) -> None:
        self.device_panel.set_enabled(self.device_panel.enable_checkbox.isChecked())
        if self.device_read_worker is not None:
            self.device_read_worker.deleteLater()
            self.device_read_worker = None

    def _start_sending(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if (
            self.device_read_worker is not None
            and self.device_read_worker.isRunning()
        ):
            self._show_error("设备端正在读取，请等待读取完成后再启动循环。")
            return
        on_command = self.on_command_edit.text()
        off_command = self.off_command_edit.text()
        if self.power_serial is None or not self.power_serial.is_open:
            self.power_panel.set_connection_status(False)
            self._show_error("请先选择串口和波特率，并完成串口连接。")
            return
        if not on_command or not off_command:
            self._show_error("ON 指令和 OFF 指令都不能为空。")
            return

        device_config = self._build_device_config_for_cycle()
        validation_message = self._validate_start_configuration(device_config)
        if validation_message:
            self._show_error(validation_message)
            return

        self.cycle_label.setText("0")
        if device_config is not None:
            self.device_panel.reset_statistics()
        self.elapsed_start_time = time.monotonic()
        self.elapsed_label.setText("00:00:00")
        self.elapsed_timer.start()
        self.worker = SendWorker(
            serial_connection=self.power_serial,
            on_command=on_command,
            off_command=off_command,
            on_delay_ms=self._delay_to_ms(self.on_delay_spin, self.on_delay_unit),
            off_delay_ms=self._delay_to_ms(self.off_delay_spin, self.off_delay_unit),
            cycle_count=self.cycle_count_spin.value(),
            device_config=device_config,
        )
        self.worker.cycle_changed.connect(
            lambda count: self.cycle_label.setText(str(count))
        )
        self.worker.status_changed.connect(self.status_label.setText)
        self.worker.command_sent.connect(
            self.power_panel.flash_connection_indicator
        )
        if device_config is not None:
            self.worker.device_verification_started.connect(
                lambda: self.device_panel.set_reading_state(device_config.mode)
            )
            self.worker.device_verification_finished.connect(
                self._show_device_result
            )
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished_normally.connect(
            lambda: self.status_label.setText("循环已结束")
        )
        self._set_running_state(True)
        self.worker.start()

    def _build_device_config_for_cycle(self) -> DeviceVerificationConfig | None:
        if not self.device_panel.enable_checkbox.isChecked():
            return None
        return self.device_panel.build_automatic_config()

    def _validate_start_configuration(
        self, device_config: DeviceVerificationConfig | None
    ) -> str | None:
        if device_config is None:
            return None
        if not device_config.port_name:
            return "启用设备端控制时，必须选择设备串口。"
        if self.power_serial is not None and (
            self.power_serial.port == device_config.port_name
        ):
            return "电源串口与设备串口不能相同。"
        if (
            device_config.mode is DeviceReadMode.SEND_AND_READ
            and not device_config.command
        ):
            return "发送并回读模式必须填写设备查询指令。"
        if not device_config.model_keyword:
            return "启用自动设备验证时，必须填写回读判断型号。"
        if device_config.read_timeout_ms <= 0:
            return "回读超时必须大于 0。"

        on_delay_ms = self._delay_to_ms(self.on_delay_spin, self.on_delay_unit)
        required_ms = (
            device_config.read_delay_ms + device_config.read_timeout_ms
        )
        if on_delay_ms < required_ms:
            return "ON 后延时必须大于等于回读前延时与回读超时之和。"
        return None

    def _stop_sending(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText("正在停止...")
            self.worker.stop()
            self.stop_button.setEnabled(False)

    def _on_worker_error(self, message: str) -> None:
        self.status_label.setText("发生错误")
        if self.power_serial is not None and self.power_serial.is_open:
            self.power_serial.close()
        self.power_serial = None
        self.power_panel.set_connection_status(False)
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
        self.device_panel.set_automatic_running_state(running)

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
        self._disconnect_power_serial()
        event.accept()
