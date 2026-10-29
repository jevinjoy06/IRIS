"""System monitoring tool."""
import platform
import subprocess

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def _get_gpu_info() -> dict | None:
    """Query GPU stats via nvidia-smi. Returns None if unavailable (no NVIDIA GPU/driver)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        name, util, mem_used, mem_total, temp = (p.strip() for p in out.stdout.strip().split(","))
        return {
            "name": name,
            "utilization_percent": float(util),
            "vram_used_mb": float(mem_used),
            "vram_total_mb": float(mem_total),
            "temperature_c": float(temp),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def get_system_info() -> dict:
    """Get system information and resource usage."""
    if not PSUTIL_AVAILABLE:
        return {
            "ok": False,
            "error": "psutil not installed",
        }

    try:
        # CPU and memory
        cpu_percent = psutil.cpu_percent(interval=1)
        vm = psutil.virtual_memory()
        ram_used_gb = vm.used / (1024**3)
        ram_total_gb = vm.total / (1024**3)
        ram_percent = vm.percent

        # Disk
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent

        # Battery (may not be available)
        battery_percent = None
        try:
            battery = psutil.sensors_battery()
            if battery:
                battery_percent = battery.percent
        except (AttributeError, Exception):
            pass

        # System info
        uname = platform.uname()
        hostname = uname.node
        os_name = uname.system
        os_version = uname.release

        return {
            "ok": True,
            "hostname": hostname,
            "os": os_name,
            "os_version": os_version,
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "ram_used_gb": round(ram_used_gb, 2),
            "ram_total_gb": round(ram_total_gb, 2),
            "disk_percent": disk_percent,
            "battery_percent": battery_percent,
            "gpu": _get_gpu_info(),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
