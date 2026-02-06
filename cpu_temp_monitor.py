"""
Hardware Temperature Monitor
============================
System Tray application that monitors CPU, GPU and SSD temperatures
and sends notifications when critical thresholds are exceeded.

Standalone - automatically downloads LibreHardwareMonitor if needed.
Requires Administrator privileges to read hardware temperatures.
"""

import sys
import os
import time
import threading
import ctypes
import subprocess
import json
import zipfile
import io
from pathlib import Path
from urllib.request import urlopen, Request

# Check for admin rights
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit()

# Hide console window
def hide_console():
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0:
        ctypes.windll.user32.ShowWindow(whnd, 0)  # SW_HIDE = 0

hide_console()

import winreg
from PIL import Image, ImageDraw, ImageFont
import pystray
from winotify import Notification, audio

# =============================================================================
# CONFIGURATION
# =============================================================================

# Critical thresholds in °C
TEMP_CRITICAL_CPU = 90    # CPU (i7-12700KF TjMax = 100°C)
TEMP_CRITICAL_GPU = 85    # GPU
TEMP_CRITICAL_SSD = 70    # SSD

# Update interval in seconds
UPDATE_INTERVAL = 3

# Notification cooldown in seconds
NOTIFICATION_COOLDOWN = 60

# Autostart name
APP_NAME = "HWTempMonitor"

# Paths
SCRIPT_DIR = Path(__file__).parent
DLL_PATH = SCRIPT_DIR / "LibreHardwareMonitorLib.dll"
PS_SCRIPT_PATH = SCRIPT_DIR / "get_cpu_temp.ps1"

# Download URL
LHM_DOWNLOAD_URL = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.4/LibreHardwareMonitor-net472.zip"

# =============================================================================
# DLL DOWNLOAD
# =============================================================================

def download_lhm_dll(progress_callback=None):
    print("\n📥 Downloading LibreHardwareMonitor...")
    
    try:
        req = Request(LHM_DOWNLOAD_URL, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urlopen(req, timeout=30) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunks = []
            
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                downloaded += len(chunk)
                
                if total_size > 0 and progress_callback:
                    progress_callback(downloaded, total_size)
            
            data = b''.join(chunks)
        
        print("\n📦 Extracting DLL...")
        
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith('LibreHardwareMonitorLib.dll'):
                    with zf.open(name) as src:
                        with open(DLL_PATH, 'wb') as dst:
                            dst.write(src.read())
                    print(f"✅ DLL saved: {DLL_PATH}")
                    return True
        
        print("❌ DLL not found in ZIP!")
        return False
        
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False

def ensure_dll_exists():
    if DLL_PATH.exists():
        return True
    
    print("=" * 50)
    print("  LibreHardwareMonitorLib.dll required")
    print("=" * 50)
    
    def progress(downloaded, total):
        percent = (downloaded / total) * 100
        bar = "█" * int(percent // 5) + "░" * (20 - int(percent // 5))
        print(f"\r   [{bar}] {percent:.0f}%", end="", flush=True)
    
    if download_lhm_dll(progress):
        return True
    
    print("\n" + "=" * 50)
    print("  MANUAL DOWNLOAD REQUIRED")
    print("=" * 50)
    print(f"\n1. Open: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases")
    print(f"2. Download 'LibreHardwareMonitor-net472.zip'")
    print(f"3. Extract 'LibreHardwareMonitorLib.dll' to:")
    print(f"   {SCRIPT_DIR}")
    
    return False

# =============================================================================
# TEMPERATURE READING
# =============================================================================

class HardwareTemperatureReader:
    """Reads hardware temperatures via PowerShell and LibreHardwareMonitor"""
    
    def __init__(self):
        self.last_error = None
        self.dll_available = DLL_PATH.exists()
    
    def _run_powershell(self) -> dict | None:
        if not self.dll_available:
            self.dll_available = DLL_PATH.exists()
            if not self.dll_available:
                return None
        
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-ExecutionPolicy", "Bypass",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File", str(PS_SCRIPT_PATH),
                    "-DllPath", str(DLL_PATH)
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.stdout.strip():
                return json.loads(result.stdout.strip())
            
            if result.stderr.strip():
                self.last_error = result.stderr.strip()
            
            return None
            
        except subprocess.TimeoutExpired:
            self.last_error = "Timeout reading temperature"
            return None
        except json.JSONDecodeError as e:
            self.last_error = f"JSON Parse Error: {e}"
            return None
        except Exception as e:
            self.last_error = str(e)
            return None
    
    def get_temperatures(self) -> dict:
        """Returns all hardware temperatures"""
        data = self._run_powershell()
        
        if not data or not data.get('success'):
            return {}
        
        result = {
            'cpu': data.get('cpu', {}).get('temp'),
            'cpu_name': data.get('cpu', {}).get('name', 'CPU'),
            'gpu': data.get('gpu', {}).get('temp'),
            'gpu_name': data.get('gpu', {}).get('name', 'GPU'),
            'ssds': []
        }
        
        for ssd in data.get('ssds', []):
            if ssd.get('temp') is not None:
                result['ssds'].append({
                    'name': ssd.get('name', 'SSD'),
                    'temp': ssd.get('temp')
                })
        
        return result
    
    def close(self):
        pass

# =============================================================================
# SYSTEM TRAY ICON
# =============================================================================

def create_temp_icon(temp: float | None, warning: bool = False, critical: bool = False, no_data: bool = False) -> Image.Image:
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    if no_data:
        bg_color = (108, 117, 125)
    elif critical:
        bg_color = (220, 53, 69)
    elif warning:
        bg_color = (255, 193, 7)
    else:
        bg_color = (40, 167, 69)
    
    draw.ellipse([2, 2, size-2, size-2], fill=bg_color)
    
    if temp is not None:
        temp_text = f"{int(temp)}"
    else:
        temp_text = "?"
    
    try:
        font = ImageFont.truetype("arial.ttf", 28)
        small_font = ImageFont.truetype("arial.ttf", 12)
    except:
        font = ImageFont.load_default()
        small_font = font
    
    bbox = draw.textbbox((0, 0), temp_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - 5
    
    draw.text((x, y), temp_text, fill='white', font=font)
    draw.text((size//2 - 6, size - 18), "°C", fill='white', font=small_font)
    
    return img

def send_notification(title: str, message: str, critical: bool = False):
    try:
        toast = Notification(
            app_id="HW Temp Monitor",
            title=title,
            msg=message,
            duration="long" if critical else "short"
        )
        
        if critical:
            toast.set_audio(audio.Default, loop=False)
        
        toast.show()
    except Exception as e:
        print(f"Notification error: {e}")

# =============================================================================
# AUTOSTART
# =============================================================================

def get_startup_registry_key():
    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_ALL_ACCESS
    )

def is_autostart_enabled() -> bool:
    try:
        key = get_startup_registry_key()
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except WindowsError:
        return False

def enable_autostart():
    try:
        key = get_startup_registry_key()
        script_path = os.path.abspath(sys.argv[0])
        
        if script_path.endswith('.py'):
            pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
            value = f'"{pythonw}" "{script_path}"'
        else:
            value = f'"{script_path}"'
        
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        send_notification("Autostart", "✅ Autostart enabled")
    except Exception as e:
        send_notification("Error", f"Could not enable autostart: {e}")

def disable_autostart():
    try:
        key = get_startup_registry_key()
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        send_notification("Autostart", "❌ Autostart disabled")
    except WindowsError:
        pass

def toggle_autostart(icon, item):
    if is_autostart_enabled():
        disable_autostart()
    else:
        enable_autostart()

# =============================================================================
# MAIN APPLICATION
# =============================================================================

class HWTempMonitor:
    """Hardware Temperature Monitor"""
    
    def __init__(self):
        self.running = True
        self.temp_reader = HardwareTemperatureReader()
        self.temps = {}
        self.last_notification_time = 0
        self.icon = None
        self.error_shown = False
        self.critical_count = 0
        
    def update_icon(self):
        if self.icon is None:
            return
        
        # Use CPU temp for icon, or highest available
        display_temp = self.temps.get('cpu')
        if display_temp is None:
            display_temp = self.temps.get('gpu')
        
        no_data = display_temp is None
        warning = display_temp is not None and display_temp >= 80
        critical = display_temp is not None and display_temp >= TEMP_CRITICAL_CPU
        
        new_icon = create_temp_icon(display_temp, warning, critical, no_data)
        self.icon.icon = new_icon
        
        # Build tooltip with all temps
        lines = []
        if self.temps.get('cpu') is not None:
            lines.append(f"CPU: {self.temps['cpu']:.0f}°C")
        if self.temps.get('gpu') is not None:
            lines.append(f"GPU: {self.temps['gpu']:.0f}°C")
        for ssd in self.temps.get('ssds', []):
            name = ssd['name'][:15] if len(ssd['name']) > 15 else ssd['name']
            lines.append(f"SSD: {ssd['temp']:.0f}°C")
        
        self.icon.title = " | ".join(lines) if lines else "No data"
    
    def check_temperatures(self):
        self.temps = self.temp_reader.get_temperatures()
        
        if not self.temps and not self.error_shown:
            if self.temp_reader.last_error:
                print(f"Error: {self.temp_reader.last_error}")
            self.error_shown = True
            return
        elif self.temps:
            self.error_shown = False
        
        # Check for critical temperatures
        critical_components = []
        
        cpu_temp = self.temps.get('cpu')
        if cpu_temp is not None and cpu_temp >= TEMP_CRITICAL_CPU:
            critical_components.append(f"CPU: {cpu_temp:.0f}°C")
        
        gpu_temp = self.temps.get('gpu')
        if gpu_temp is not None and gpu_temp >= TEMP_CRITICAL_GPU:
            critical_components.append(f"GPU: {gpu_temp:.0f}°C")
        
        for ssd in self.temps.get('ssds', []):
            if ssd['temp'] >= TEMP_CRITICAL_SSD:
                critical_components.append(f"SSD: {ssd['temp']:.0f}°C")
        
        current_time = time.time()
        time_since_last = current_time - self.last_notification_time
        
        if critical_components:
            self.critical_count += 1
        else:
            self.critical_count = 0
        
        if self.critical_count >= 2 and time_since_last >= NOTIFICATION_COOLDOWN:
            send_notification(
                "🔥 CRITICAL TEMPERATURE!",
                "\n".join(critical_components) + "\nCheck your system cooling!",
                critical=True
            )
            self.last_notification_time = current_time
    
    def monitoring_loop(self):
        while self.running:
            try:
                self.check_temperatures()
                self.update_icon()
            except Exception as e:
                print(f"Error: {e}")
            
            time.sleep(UPDATE_INTERVAL)
    
    def quit_app(self, icon=None, item=None):
        self.running = False
        self.temp_reader.close()
        if self.icon:
            self.icon.stop()
    
    def create_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                "Autostart",
                toggle_autostart,
                checked=lambda item: is_autostart_enabled()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Quit",
                self.quit_app
            )
        )
    
    def run(self):
        initial_icon = create_temp_icon(None, no_data=True)
        
        self.icon = pystray.Icon(
            "hw_temp_monitor",
            initial_icon,
            "HW Temp Monitor",
            menu=self.create_menu()
        )
        
        monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        monitor_thread.start()
        
        self.icon.run()

# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  Hardware Temperature Monitor")
    print("=" * 50)
    print(f"\n⚙️  Critical thresholds:")
    print(f"   • CPU: {TEMP_CRITICAL_CPU}°C")
    print(f"   • GPU: {TEMP_CRITICAL_GPU}°C")
    print(f"   • SSD: {TEMP_CRITICAL_SSD}°C")
    print(f"   • Update interval: {UPDATE_INTERVAL}s")
    
    if not ensure_dll_exists():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    print(f"\n✅ LibreHardwareMonitorLib.dll found")
    print(f"\n💡 Running in system tray.")
    print("   Right-click icon for options.\n")
    
    try:
        monitor = HWTempMonitor()
        monitor.run()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
