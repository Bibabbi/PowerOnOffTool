# PowerOnOffTool

一个基于 PyQt6 的图形界面应用程序，用于向串行设备发送 ON/OFF 命令序列，支持自定义延时。适用于控制电源循环、继电器开关或任何需要重复 ON/OFF 命令的设备。

## ✨ 功能特性

- 🖥️ **用户友好的图形界面** - 基于 PyQt6 构建，直观易用
- 🔌 **串口管理** - 自动检测和配置可用的 COM 端口
- ⚙️ **灵活的波特率设置** - 支持常见波特率（9600、19200、38400、57600、115200）
- ⏱️ **可自定义延时** - 在 ON 和 OFF 命令之间设置延时，支持多种时间单位（毫秒、秒、分钟）
- 🔄 **循环计数** - 实时监控已完成的 ON/OFF 循环次数
- 🛑 **开始/停止控制** - 随时轻松启动和停止命令序列
- 📊 **状态更新** - 实时反馈当前操作状态
- 🧵 **线程操作** - 使用工作线程实现非阻塞式串口通信

## 📋 系统要求

- Python 3.7+
- PyQt6 (6.11.0+)
- pyserial (3.5+)

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/zhbi98/PowerOnOffTool.git
cd PowerOnOffTool

# 安装依赖包
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

## 📖 使用指南

### 第一步：配置串口

1. 从**串口**下拉菜单中选择您的 USB 转串口设备
   - 显示格式：`{端口名} - {设备描述}`（例如：`COM3 - USB Serial Device`）
2. 点击**刷新**按钮检测可用端口（自动刷新已连接设备）
3. 从**波特率**下拉菜单中选择合适的波特率
   - 可选值：9600, 19200, 38400, 57600, 115200
   - 默认值：9600

### 第二步：设置命令

1. 在 **ON 指令**输入框中输入 ON 命令
   - 支持任意 UTF-8 编码文本
   - 例如：`ON`、`START`、`1` 等
2. 在 **OFF 指令**输入框中输入 OFF 命令
   - 例如：`OFF`、`STOP`、`0` 等

### 第三步：配置延时

1. 设置 **ON 后延时** - 发送 ON 命令后的等待时间
2. 设置 **OFF 后延时** - 发送 OFF 命令后的等待时间
3. 在时间单位下拉菜单中选择：
   - `毫秒`（ms）- 用于高精度短延时
   - `秒`（s）- 用于一般延时
   - `分钟`（min）- 用于长延时

**示例：**
- ON 延时 = 500 毫秒，OFF 延时 = 1 秒

### 第四步：执行

1. 点击**启动**按钮开始发送命令循环
2. 实时监控：
   - **完成循环次数** - 已完成的 ON/OFF 循环数
   - **状态消息** - 当前操作状态
3. 点击**停止**按钮暂停操作

## 🔧 工作流程

```
应用启动
  ↓
配置串口参数（端口、波特率、命令、延时）
  ↓
点击"启动"按钮
  ↓
打开串口连接（配置的波特率）
  ↓
循环执行（直至用户停止）：
  ├─ 发送 ON 命令（UTF-8 编码）
  ├─ 等待 ON 延时
  ├─ 发送 OFF 命令（UTF-8 编码）
  ├─ 等待 OFF 延时
  └─ 循环计数 +1
  ↓
点击"停止"按钮或发生错误
  ↓
关闭串口连接
  ↓
显示最终状态
```

## 🏗️ 架构设计

### 类设计

#### **SendWorker（工作线程）**
继承自 `QThread`，在独立线程中处理串口通信：

```python
class SendWorker(QThread):
    # 信号定义
    cycle_changed = pyqtSignal(int)        # 循环次数变化
    status_changed = pyqtSignal(str)       # 状态消息变化
    error_occurred = pyqtSignal(str)       # 错误发生
    finished_normally = pyqtSignal()       # 正常完成
```

**主要方法：**
- `run()` - 执行主循环，打开串口、发送命令、控制延时
- `stop()` - 请求停止（设置 `_stop_requested` 标志）
- `_send_command(command)` - 发送 UTF-8 编码的命令
- `_wait_ms(milliseconds)` - 精确延时（支持中断）

**串口配置：**
```python
serial.Serial(
    port=port_name,
    baudrate=baudrate,
    bytesize=serial.EIGHTBITS,      # 8 位数据位
    parity=serial.PARITY_NONE,      # 无奇偶校验
    stopbits=serial.STOPBITS_ONE,   # 1 位停止位
    timeout=1,                       # 1 秒读超时
)
```

#### **MainWindow（主窗口）**
管理用户界面和应用逻辑：

**UI 组件：**
- 串口设置组：端口选择、波特率设置、刷新按钮
- 发送指令组：ON/OFF 命令输入框
- 延时设置组：ON/OFF 延时输入和时间单位选择
- 控制按钮：启动、停止
- 状态显示：循环次数、状态消息

**主要方法：**
- `_refresh_ports()` - 自动检测可用串口
- `_start_sending()` - 验证参数并启动工作线程
- `_stop_sending()` - 请求停止工作线程
- `_delay_to_ms()` - 将延时值转换为毫秒

### 线程安全设计

使用 **PyQt6 信号-槽机制** 实现线程安全通信：

```python
# 工作线程 → 主线程（安全）
worker.cycle_changed.connect(lambda count: update_ui(count))
worker.status_changed.connect(update_status)
worker.error_occurred.connect(show_error)
```

**优势：**
- GUI 不会因串口操作阻塞
- 跨线程通信自动序列化
- 异常处理完善，错误安全

## 📊 状态消息

应用在运行过程中会显示以下状态消息：

| 状态消息 | 含义 | 何时出现 |
|---------|------|---------|
| 已连接 {port} | 串口连接成功 | 启动后立即 |
| 已发送：{command} | 命令发送成功 | 每次发送 ON/OFF 时 |
| 已停止 | 用户主动停止 | 点击停止按钮后 |
| 循环已结束 | 循环正常完成 | 工作线程正常退出 |
| 串口错误：{error} | 串口连接失败 | 端口不存在、设备断开等 |
| 发送失败：{error} | 命令发送异常 | 串口关闭、设备故障等 |

## ⚙️ 配置参数

所有设置均可通过 GUI 配置，无需修改代码：

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| 波特率 | 9600 | 9600, 19200, 38400, 57600, 115200 | 必须与设备匹配 |
| ON 延时 | 1000 | 0 - 3,600,000 | 支持小数值 |
| OFF 延时 | 1000 | 0 - 3,600,000 | 支持小数值 |
| 时间单位 | 毫秒 | 毫秒、秒、分钟 | 自动转换为毫秒 |

**时间单位转换：**
- 毫秒：×1
- 秒：×1000
- 分钟：×60000

## 🛡️ 错误处理

应用程序包含全面的错误处理机制：

### 验证层
- ✅ 端口检查 - 确保已选择有效端口
- ✅ 命令检查 - ON/OFF 命令不能为空
- ✅ 参数检查 - 延时值有效范围检查

### 串口层
- ✅ 连接错误 - 捕获 `SerialException`，显示错误原因
- ✅ 通信错误 - 捕获发送/接收异常
- ✅ 自动关闭 - 异常时自动关闭串口

### 应用层
- ✅ 重复启动防护 - 防止多个工作线程同时运行
- ✅ 优雅关闭 - 窗口关闭时等待工作线程完成（最多 2 秒）
- ✅ 资源清理 - 线程正常退出后删除对象

### 异常处理示例
```python
try:
    # 尝试连接和发送
    ...
except serial.SerialException as exc:
    # 串口特定错误
    emit_error(f"串口错误：{exc}")
except Exception as exc:
    # 其他异常
    emit_error(f"发送失败：{exc}")
finally:
    # 确保资源释放
    if serial is not None:
        serial.close()
```

## 🔗 常见用途

- 🔋 **电源循环测试** - 自动化测试设备启动/关闭
- 🔌 **继电器控制** - 控制继电器模块开关
- ⚙️ **设备初始化** - 按指定序列控制硬件
- 🤖 **自动化测试** - 集成到测试框架中
- 📡 **通信调试** - 调试串口设备

## 📁 项目结构

```
PowerOnOffTool/
├── main.py              # 应用程序主文件（410 行）
│   ├── SendWorker       # 工作线程类（~100 行）
│   └── MainWindow       # 主窗口类（~200 行）
├── requirements.txt     # 依赖配置文件
└── README.md           # 本文档
```

### 代码统计
- **总行数**：约 320 行（包括注释和空行）
- **主类**：2 个（SendWorker, MainWindow）
- **信号**：4 个（cycle_changed, status_changed, error_occurred, finished_normally）
- **依赖**：2 个（PyQt6, pyserial）

## 🎯 高级用法

### 最小延时
最小有效延时为 1 毫秒，但实际精度取决于操作系统调度：

```python
# 实现 1ms 精确延时
def _wait_ms(self, milliseconds: float) -> bool:
    end_time = time.monotonic() + milliseconds / 1000
    while not self._stop_requested:
        remaining = end_time - time.monotonic()
        if remaining <= 0:
            return False
        self.msleep(min(50, max(1, int(remaining * 1000))))
    return True
```

### 命令编码
所有命令使用 UTF-8 编码发送：

```python
self._serial.write(command.encode("utf-8"))  # 支持中文等字符
self._serial.flush()                          # 确保立即发送
```

### 停止响应性
工作线程检查停止标志的频率：
- 每个命令发送后
- 每个延时周期内（50ms 间隔检查）

确保用户点击"停止"后快速响应。

## 📝 许可证

本项目按原样提供。

## 👤 作者

由 [Bibabbi](https://github.com/Bibabbi) 创建

---

## ❓ 常见问题

**Q: 如何选择正确的波特率？**  
A: 查看您的设备文档或试用。最常见的是 9600 和 115200。

**Q: 支持多个并发连接吗？**  
A: 不支持。需要控制多个设备时，请运行多个应用实例。

**Q: 如何自定义 ON/OFF 命令？**  
A: 在输入框中输入任何字符串即可，应用会原样发送。

**Q: 延时精度如何保证？**  
A: 使用 `time.monotonic()` 计时，在循环中以 50ms 间隔检查，精度约 ±50ms。

**Q: 关闭窗口时会怎样？**  
A: 应用会等待工作线程最多 2 秒后强制关闭，确保没有僵尸进程。

**Q: 支持哪些字符编码？**  
A: 支持 UTF-8 编码的所有字符，包括中文、特殊符号等。

