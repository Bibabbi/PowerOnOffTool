from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.constants import BAUDRATES


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
        self.connection_button = QPushButton("连接")
        self.connection_indicator = QLabel()
        self.connection_indicator.setFixedSize(12, 12)
        self._connection_state: Optional[bool] = None
        self._indicator_flash_timer = QTimer(self)
        self._indicator_flash_timer.setSingleShot(True)
        self._indicator_flash_timer.timeout.connect(self._restore_connection_indicator)
        baud_row = QHBoxLayout()
        baud_row.addWidget(self.baud_combo, 1)
        baud_row.addWidget(self.connection_button)
        baud_row.addWidget(self.connection_indicator)
        form.addRow("波特率：", baud_row)
        self.set_connection_status(None)
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
        self.cycle_count_spin = QSpinBox()
        self.cycle_count_spin.setRange(1, 1_000_000)
        self.cycle_count_spin.setValue(1)
        self.cycle_count_spin.setSuffix(" 次")
        form.addRow(
            "ON 后延时：", self._delay_row(self.on_delay_spin, self.on_delay_unit)
        )
        form.addRow(
            "OFF 后延时：", self._delay_row(self.off_delay_spin, self.off_delay_unit)
        )
        form.addRow("循环次数：", self.cycle_count_spin)
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
        layout.addWidget(QLabel("完成开关的循环次数："))
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
            self.connection_button,
            self.on_command_edit,
            self.off_command_edit,
            self.on_delay_spin,
            self.off_delay_spin,
            self.on_delay_unit,
            self.off_delay_unit,
            self.cycle_count_spin,
        ):
            widget.setEnabled(enabled)
        self.start_button.setEnabled(enabled)
        self.stop_button.setEnabled(running)

    def set_connection_status(self, connected: Optional[bool]) -> None:
        self._connection_state = connected
        self._indicator_flash_timer.stop()
        self._restore_connection_indicator()
        if connected is True:
            self.connection_button.setText("断开")
        elif connected is False:
            self.connection_button.setText("连接")
        else:
            self.connection_button.setText("连接")

    def flash_connection_indicator(self) -> None:
        if self._connection_state is not True:
            return
        self.connection_indicator.setStyleSheet(
            "background-color: #86efac; border-radius: 6px;"
        )
        self.connection_indicator.setToolTip("正在发送指令")
        self._indicator_flash_timer.start(160)

    def _restore_connection_indicator(self) -> None:
        if self._connection_state is True:
            color = "#16a34a"
            tooltip = "串口已连接"
        elif self._connection_state is False:
            color = "#dc2626"
            tooltip = "串口连接失败"
        else:
            color = "#6b7280"
            tooltip = "串口未连接"
        self.connection_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 6px;"
        )
        self.connection_indicator.setToolTip(tooltip)
