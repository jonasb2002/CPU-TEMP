# HW Temp Monitor 🌡️

A lightweight Windows system tray application that monitors CPU, GPU and SSD temperatures in real-time.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## Features

- 🌡️ **Live temperature display** in system tray icon (shows CPU temp)
- 📊 **All temperatures visible** in tooltip (hover over icon)
- 🔥 **Critical alerts only** - no notification spam
- 🚀 **Autostart option** - runs on Windows startup
- 💨 **Silent operation** - runs completely in background
- 📦 **Standalone** - automatically downloads required libraries

## Screenshot

```
Tray Icon: [72°C] (green/yellow/red based on temperature)

Tooltip: CPU: 72°C | GPU: 55°C | SSD: 38°C
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/jonasb2002/CPU-TEMP.git
cd CPU-TEMP
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
python cpu_temp_monitor.py
```

> ⚠️ **Administrator privileges required** - The app will automatically request elevation to read hardware sensors.

On first run, the app automatically downloads `LibreHardwareMonitorLib.dll` from the official LibreHardwareMonitor releases.

## Critical Temperature Thresholds

| Component | Critical Threshold |
|-----------|-------------------|
| CPU       | 90°C              |
| GPU       | 85°C              |
| SSD       | 70°C              |

Notifications are only sent when a component stays critical for **2 consecutive readings** (6+ seconds) to avoid false alarms from temporary spikes.

## Configuration

Edit the thresholds in `cpu_temp_monitor.py`:

```python
TEMP_CRITICAL_CPU = 90    # CPU critical temperature
TEMP_CRITICAL_GPU = 85    # GPU critical temperature
TEMP_CRITICAL_SSD = 70    # SSD critical temperature
UPDATE_INTERVAL = 3       # Update interval in seconds
```

## Requirements

- Windows 10/11
- Python 3.10+
- Administrator privileges

## Dependencies

- `pystray` - System tray icon
- `Pillow` - Icon generation
- `winotify` - Windows notifications
- `pywin32` - Windows registry access

## How It Works

The app uses [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) via PowerShell to read hardware sensors. This approach works with Python 3.10+ without requiring the `pythonnet` package.

## License

MIT License
