from typing import Optional

from serial.tools import list_ports
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import BAUDRATES
from app.models import DeviceReadMode, DeviceReadResult, DeviceVerificationConfig


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
        self._automatic_running = False
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
        group = QGroupBox("回读配置")
        form = QFormLayout(group)

        self.device_command_edit = QLineEdit()
        self.device_command_edit.setPlaceholderText("输入示例：*IDN?\\r\\n")
        self.device_model_edit = QLineEdit()
        self.device_model_edit.setPlaceholderText(
            "输入示例：MODEL-123 或设备型号关键字"
        )
        self.auto_mode_combo = QComboBox()
        self.auto_mode_combo.addItem("发送并回读", DeviceReadMode.SEND_AND_READ)
        self.auto_mode_combo.addItem("仅回读", DeviceReadMode.READ_ONLY)
        self.read_delay_spin, self.read_delay_unit = self._create_delay_controls(0)
        self.read_timeout_spin, self.read_timeout_unit = self._create_delay_controls(2)
        self.read_timeout_unit.setCurrentText("s")
        self.device_read_button = QPushButton("发送并回读")
        self.device_read_only_button = QPushButton("仅回读")
        button_row = QHBoxLayout()
        button_row.addWidget(self.device_read_button)
        button_row.addWidget(self.device_read_only_button)
        form.addRow("发送指令：", self.device_command_edit)
        form.addRow("回读判断型号：", self.device_model_edit)
        form.addRow("自动验证模式：", self.auto_mode_combo)
        form.addRow("回读前延时：", self._delay_row(self.read_delay_spin, self.read_delay_unit))
        form.addRow("回读超时：", self._delay_row(self.read_timeout_spin, self.read_timeout_unit))
        form.addRow("", button_row)
        return group

    def _create_status_group(self) -> QGroupBox:
        group = QGroupBox("设备状态")
        form = QFormLayout(group)

        self.connection_label = QLabel("未连接")
        self.current_result_label = QLabel("未执行")
        self.read_count_label = QLabel("0")
        self.query_count_label = QLabel("0")
        self.pass_count_label = QLabel("0")
        self.fail_count_label = QLabel("0")
        self.last_action_label = QLabel("无")
        form.addRow("连接状态：", self.connection_label)
        form.addRow("本轮结果：", self.current_result_label)
        form.addRow("读取次数：", self.read_count_label)
        form.addRow("查询指令次数：", self.query_count_label)
        form.addRow("成功次数：", self.pass_count_label)
        form.addRow("失败次数：", self.fail_count_label)
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
        enabled = enabled and not self._automatic_running
        for widget in (
            self.device_port_combo,
            self.device_refresh_button,
            self.device_baud_combo,
            self.device_command_edit,
            self.device_model_edit,
            self.auto_mode_combo,
            self.read_delay_spin,
            self.read_delay_unit,
            self.read_timeout_spin,
            self.read_timeout_unit,
            self.device_read_button,
            self.device_read_only_button,
        ):
            widget.setEnabled(enabled)

    @staticmethod
    def _create_delay_controls(default_value: float) -> tuple[QDoubleSpinBox, QComboBox]:
        spin = QDoubleSpinBox()
        spin.setRange(0, 3600000)
        spin.setDecimals(3)
        spin.setSingleStep(100)
        spin.setValue(default_value)
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

    def build_config(self, mode: DeviceReadMode) -> DeviceVerificationConfig:
        return DeviceVerificationConfig(
            port_name=self.device_port_combo.currentData() or "",
            baudrate=int(self.device_baud_combo.currentText()),
            command=self.device_command_edit.text(),
            model_keyword=self.device_model_edit.text().strip(),
            mode=mode,
            read_delay_ms=self._delay_to_ms(self.read_delay_spin, self.read_delay_unit),
            read_timeout_ms=self._delay_to_ms(
                self.read_timeout_spin, self.read_timeout_unit
            ),
        )

    def build_automatic_config(self) -> DeviceVerificationConfig:
        return self.build_config(self.auto_mode_combo.currentData())

    @staticmethod
    def _delay_to_ms(spin: QDoubleSpinBox, unit: QComboBox) -> float:
        return spin.value() * float(unit.currentData())

    def set_automatic_running_state(self, running: bool) -> None:
        self._automatic_running = running
        self.enable_checkbox.setEnabled(not running)
        self.set_enabled(self.enable_checkbox.isChecked())

    def set_reading_state(self, mode: DeviceReadMode) -> None:
        action = "发送并回读" if mode is DeviceReadMode.SEND_AND_READ else "仅回读"
        self.connection_label.setText("读取中")
        self.current_result_label.setText("等待中")
        self.last_action_label.setText(action)
        self.readback_output.setPlainText("正在等待设备回读...")

    def reset_statistics(self) -> None:
        for label in (
            self.read_count_label,
            self.query_count_label,
            self.pass_count_label,
            self.fail_count_label,
        ):
            label.setText("0")
        self.current_result_label.setText("未执行")

    def show_result(self, result: DeviceReadResult) -> None:
        status_text = {
            "pass": "PASS",
            "fail": "FAIL",
            "timeout": "超时",
            "error": "通信错误",
            "cancelled": "已取消",
            "unjudged": "未判断",
        }[result.status]
        self.current_result_label.setText(status_text)
        self.connection_label.setText("错误" if result.status == "error" else "已完成")

        tx_text = (
            self._format_serial_text(result.transmitted)
            if result.transmitted
            else "未发送"
        )
        rx_text = (
            self._format_serial_text(result.response).strip()
            if result.response
            else result.error_message or "无接收数据"
        )
        self.readback_output.setPlainText(
            f"TX：{tx_text}\nRX：{rx_text}"
        )

        if result.status != "cancelled":
            self._increment(self.read_count_label)
        if result.query_sent:
            self._increment(self.query_count_label)
        if result.status == "pass":
            self._increment(self.pass_count_label)
        elif result.status in {"fail", "timeout", "error"}:
            self._increment(self.fail_count_label)

    @staticmethod
    def _increment(label: QLabel) -> None:
        label.setText(str(int(label.text()) + 1))

    @staticmethod
    def _format_serial_text(data: bytes) -> str:
        return (
            data.decode("utf-8", errors="replace")
            .replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )

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
