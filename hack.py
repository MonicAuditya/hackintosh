#!/usr/bin/env python3

import os
import sys
import json
import platform
import subprocess
import shutil
import glob
from datetime import datetime


OUTPUT = "Hackintosh_Hardware_Report.json"


def run(cmd, timeout=30):
    """Run a command and return stdout."""
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return {
            "returncode": p.returncode,
            "stdout": p.stdout.strip(),
            "stderr": p.stderr.strip()
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e)
        }


def command_exists(name):
    return shutil.which(name) is not None


def cmd_text(cmd, timeout=30):
    r = run(cmd, timeout)
    return r["stdout"]


def read_file(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read().strip()
    except Exception:
        return None


def read_sysfs(path):
    value = read_file(path)
    return value


def get_command_output(command, args=None, timeout=30):
    args = args or []

    if not command_exists(command):
        return None

    return cmd_text([command] + args, timeout)


def collect_basic_system():
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "kernel_full": platform.version(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "boot_time": cmd_text(["uptime", "-s"]) if command_exists("uptime") else None,
        "date": datetime.now().isoformat()
    }


def collect_cpu():
    data = {}

    if command_exists("lscpu"):
        raw = get_command_output("lscpu")
        data["lscpu"] = raw

        parsed = {}

        for line in raw.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                parsed[key.strip()] = value.strip()

        data["summary"] = parsed

    data["proc_cpuinfo"] = read_file("/proc/cpuinfo")

    return data


def collect_memory():
    data = {}

    if command_exists("free"):
        data["free"] = get_command_output("free", ["-h"])

    if command_exists("dmidecode"):
        data["memory_dmi"] = get_command_output(
            "dmidecode",
            ["-t", "memory"],
            30
        )

    return data


def collect_gpu_and_pci():
    data = {}

    if command_exists("lspci"):
        data["lspci"] = get_command_output("lspci")
        data["lspci_nn"] = get_command_output("lspci", ["-nn"])
        data["lspci_nnk"] = get_command_output("lspci", ["-nnk"])
        data["lspci_verbose"] = get_command_output("lspci", ["-vv"])

        gpu_lines = []

        for line in data["lspci_nn"].splitlines():
            low = line.lower()

            if any(x in low for x in [
                "vga",
                "3d controller",
                "display controller"
            ]):
                gpu_lines.append(line)

        data["gpu_devices"] = gpu_lines

    return data


def collect_usb():
    data = {}

    if command_exists("lsusb"):
        data["lsusb"] = get_command_output("lsusb")
        data["lsusb_tree"] = get_command_output("lsusb", ["-t"])

    return data


def collect_network():
    data = {}

    if command_exists("ip"):
        data["interfaces"] = get_command_output(
            "ip", ["-details", "address"]
        )

        data["links"] = get_command_output(
            "ip", ["-details", "link"]
        )

    if command_exists("lspci"):
        raw = get_command_output("lspci", ["-nnk"])

        network = []

        for line in raw.splitlines():
            low = line.lower()

            if any(x in low for x in [
                "ethernet controller",
                "network controller",
                "wireless controller"
            ]):
                network.append(line)

        data["pci_network_devices"] = network

    # Network driver information
    drivers = {}

    net_path = "/sys/class/net"

    if os.path.exists(net_path):
        for interface in os.listdir(net_path):
            driver_link = f"{net_path}/{interface}/device/driver"

            try:
                driver = os.path.basename(os.readlink(driver_link))
            except Exception:
                driver = None

            drivers[interface] = {
                "driver": driver,
                "address": read_sysfs(
                    f"{net_path}/{interface}/address"
                ),
                "operstate": read_sysfs(
                    f"{net_path}/{interface}/operstate"
                )
            }

    data["interface_details"] = drivers

    return data


def collect_bluetooth():
    data = {}

    if command_exists("bluetoothctl"):
        data["bluetoothctl"] = get_command_output(
            "bluetoothctl",
            ["show"]
        )

    if command_exists("lsusb"):
        raw = get_command_output("lsusb")

        bluetooth = []

        for line in raw.splitlines():
            if "Bluetooth" in line or "bluetooth" in line:
                bluetooth.append(line)

        data["usb_bluetooth_devices"] = bluetooth

    return data


def collect_audio():
    data = {}

    if command_exists("lspci"):
        raw = get_command_output("lspci", ["-nnk"])

        audio = []

        for line in raw.splitlines():
            low = line.lower()

            if any(x in low for x in [
                "audio device",
                "multimedia audio",
                "audio controller"
            ]):
                audio.append(line)

        data["pci_audio_devices"] = audio

    if command_exists("aplay"):
        data["alsa_devices"] = get_command_output(
            "aplay",
            ["-l"]
        )

    if command_exists("pactl"):
        data["pulse_audio"] = get_command_output(
            "pactl",
            ["list", "short", "sinks"]
        )

    return data


def collect_storage():
    data = {}

    if command_exists("lsblk"):
        data["lsblk"] = get_command_output(
            "lsblk",
            ["-o", "NAME,KNAME,MODEL,SERIAL,SIZE,TYPE,FSTYPE,FSVER,MOUNTPOINTS,TRAN"]
        )

        data["lsblk_json"] = get_command_output(
            "lsblk",
            ["-J", "-O"]
        )

    if command_exists("blkid"):
        data["blkid"] = get_command_output("blkid")

    if command_exists("nvme"):
        data["nvme_list"] = get_command_output(
            "nvme",
            ["list"]
        )

    return data


def collect_motherboard_bios():
    data = {}

    if command_exists("dmidecode"):
        data["system"] = get_command_output(
            "dmidecode",
            ["-t", "system"]
        )

        data["baseboard"] = get_command_output(
            "dmidecode",
            ["-t", "baseboard"]
        )

        data["bios"] = get_command_output(
            "dmidecode",
            ["-t", "bios"]
        )

        data["chassis"] = get_command_output(
            "dmidecode",
            ["-t", "chassis"]
        )

        data["processor"] = get_command_output(
            "dmidecode",
            ["-t", "processor"]
        )

    # Direct sysfs fallback
    dmi = {}

    dmi_paths = {
        "sys_vendor": "/sys/class/dmi/id/sys_vendor",
        "product_name": "/sys/class/dmi/id/product_name",
        "product_version": "/sys/class/dmi/id/product_version",
        "board_vendor": "/sys/class/dmi/id/board_vendor",
        "board_name": "/sys/class/dmi/id/board_name",
        "board_version": "/sys/class/dmi/id/board_version",
        "bios_vendor": "/sys/class/dmi/id/bios_vendor",
        "bios_version": "/sys/class/dmi/id/bios_version",
        "bios_date": "/sys/class/dmi/id/bios_date",
    }

    for key, path in dmi_paths.items():
        dmi[key] = read_sysfs(path)

    data["sysfs_dmi"] = dmi

    return data


def collect_acpi():
    data = {}

    acpi_dir = "/sys/firmware/acpi/tables"

    if os.path.exists(acpi_dir):
        tables = []

        for item in sorted(os.listdir(acpi_dir)):
            path = os.path.join(acpi_dir, item)

            try:
                size = os.path.getsize(path)
            except Exception:
                size = None

            tables.append({
                "name": item,
                "size": size
            })

        data["available_tables"] = tables

    # Copy ACPI tables if accessible
    acpi_dump_dir = "ACPI_Tables"

    try:
        os.makedirs(acpi_dump_dir, exist_ok=True)

        if os.path.exists(acpi_dir):
            for item in os.listdir(acpi_dir):
                src = os.path.join(acpi_dir, item)
                dst = os.path.join(acpi_dump_dir, item)

                try:
                    with open(src, "rb") as f:
                        content = f.read()

                    with open(dst, "wb") as f:
                        f.write(content)

                except Exception:
                    pass

    except Exception:
        pass

    data["dump_directory"] = acpi_dump_dir

    return data


def collect_input_devices():
    data = {}

    if command_exists("libinput"):
        data["libinput_devices"] = get_command_output(
            "libinput",
            ["list-devices"]
        )

    if command_exists("lsusb"):
        data["usb_input"] = get_command_output(
            "lsusb"
        )

    # Linux input devices
    input_dir = "/proc/bus/input/devices"

    if os.path.exists(input_dir):
        data["proc_input_devices"] = read_file(input_dir)

    return data


def collect_display():
    data = {}

    if command_exists("xrandr"):
        data["xrandr"] = get_command_output(
            "xrandr",
            ["--props"]
        )

    # DRM connectors
    drm = {}

    drm_path = "/sys/class/drm"

    if os.path.exists(drm_path):
        for item in sorted(os.listdir(drm_path)):
            if "-" not in item:
                continue

            status = read_sysfs(
                f"{drm_path}/{item}/status"
            )

            modes = read_file(
                f"{drm_path}/{item}/modes"
            )

            drm[item] = {
                "status": status,
                "modes": modes
            }

    data["drm"] = drm

    return data


def collect_battery():
    data = {}

    battery_path = "/sys/class/power_supply"

    if os.path.exists(battery_path):
        for item in os.listdir(battery_path):
            path = os.path.join(battery_path, item)

            if item.startswith("BAT"):
                battery = {}

                for filename in [
                    "manufacturer",
                    "model_name",
                    "serial_number",
                    "technology",
                    "status",
                    "capacity",
                    "capacity_level",
                    "voltage_now",
                    "current_now",
                    "power_now",
                    "energy_full",
                    "energy_full_design"
                ]:
                    battery[filename] = read_sysfs(
                        os.path.join(path, filename)
                    )

                data[item] = battery

    return data


def collect_sensors():
    data = {}

    if command_exists("sensors"):
        data["lm_sensors"] = get_command_output(
            "sensors"
        )

    return data


def collect_loaded_modules():
    data = {}

    if command_exists("lsmod"):
        data["lsmod"] = get_command_output(
            "lsmod"
        )

    return data


def collect_lshw():
    if not command_exists("lshw"):
        return None

    result = run(
        ["lshw", "-json"],
        timeout=60
    )

    if result["returncode"] == 0:
        try:
            return json.loads(result["stdout"])
        except Exception:
            return result["stdout"]

    return result["stderr"]


def collect_efi():
    data = {}

    efi_vars = "/sys/firmware/efi"

    data["efi_present"] = os.path.exists(efi_vars)

    if os.path.exists(efi_vars):
        data["efi_variables"] = os.listdir(efi_vars)

    if command_exists("efibootmgr"):
        data["efibootmgr"] = get_command_output(
            "efibootmgr",
            ["-v"]
        )

    return data


def collect_kernel_cmdline():
    return read_file("/proc/cmdline")


def collect_all():
    print("Collecting Hackintosh hardware information...")
    print()

    report = {
        "report_info": {
            "tool": "Linux Hackintosh Hardware Reporter",
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "note": (
                "This report is intended for macOS/OpenCore "
                "hardware compatibility analysis."
            )
        },

        "system": collect_basic_system(),

        "cpu": collect_cpu(),

        "memory": collect_memory(),

        "gpu_and_pci": collect_gpu_and_pci(),

        "usb": collect_usb(),

        "network": collect_network(),

        "bluetooth": collect_bluetooth(),

        "audio": collect_audio(),

        "storage": collect_storage(),

        "motherboard_and_bios": collect_motherboard_bios(),

        "acpi": collect_acpi(),

        "input_devices": collect_input_devices(),

        "display": collect_display(),

        "battery": collect_battery(),

        "sensors": collect_sensors(),

        "kernel_modules": collect_loaded_modules(),

        "efi": collect_efi(),

        "kernel_cmdline": collect_kernel_cmdline(),

        "lshw": collect_lshw()
    }

    return report


def main():

    if os.geteuid() != 0:
        print("WARNING:")
        print("Run this script with sudo for the most complete report.")
        print()
        print("Example:")
        print("  sudo python3 hackintosh_report.py")
        print()

    report = collect_all()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("=" * 60)
    print("REPORT COMPLETE")
    print("=" * 60)
    print()
    print(f"JSON report: {os.path.abspath(OUTPUT)}")
    print()

    print("Important GPU devices found:")

    for gpu in report["gpu_and_pci"].get("gpu_devices", []):
        print("  ", gpu)

    print()
    print("ACPI tables were saved to:")
    print(f"  {os.path.abspath('ACPI_Tables')}")
    print()


if __name__ == "__main__":
    main()
