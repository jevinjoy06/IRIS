"""System monitoring tool."""
import platform

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


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
        hostname = uname.nodename
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
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
