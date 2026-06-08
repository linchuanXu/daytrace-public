"""ADB communication layer."""

import subprocess
import shutil
from typing import Optional


class ADBError(Exception):
    pass


class ADB:
    def __init__(self, adb_path: Optional[str] = None, serial: Optional[str] = None):
        self.adb_bin = adb_path or shutil.which("adb") or "adb"
        self.serial = serial

    def _base_cmd(self) -> list[str]:
        cmd = [self.adb_bin]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def run(self, *args: str, timeout: int = 60) -> str:
        cmd = self._base_cmd() + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            raise ADBError(f"ADB command timed out: {' '.join(args)}")
        except FileNotFoundError:
            raise ADBError(f"ADB executable not found: {self.adb_bin}")

    def shell(self, command: str, timeout: int = 60) -> str:
        return self.run("shell", command, timeout=timeout)

    def check_connection(self) -> dict:
        """Check device connection and return device info."""
        devices_out = self.run("devices")
        lines = [l.strip() for l in devices_out.strip().splitlines()]
        connected = [l for l in lines[1:] if l.endswith("\tdevice")]
        if not connected:
            raise ADBError("No Android device connected via ADB. Check USB connection and developer mode.")

        brand = self.shell("getprop ro.product.brand").strip()
        model = self.shell("getprop ro.product.model").strip()
        android_ver = self.shell("getprop ro.build.version.release").strip()
        sdk = self.shell("getprop ro.build.version.sdk").strip()
        serial = connected[0].split("\t")[0]

        return {
            "serial": serial,
            "brand": brand,
            "model": model,
            "android_version": android_ver,
            "sdk": sdk,
            "display": f"{brand} {model} (Android {android_ver})",
        }

    def get_user_packages(self) -> list[str]:
        """Return list of user-installed (third-party) package names."""
        out = self.shell("pm list packages -3")
        packages = []
        for line in out.strip().splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line[len("package:"):].strip())
        return packages

    def dumpsys(self, service: str, args: str = "", timeout: int = 90) -> str:
        cmd = f"dumpsys {service}"
        if args:
            cmd += f" {args}"
        return self.shell(cmd, timeout=timeout)

    def pull(self, remote: str, local: str, timeout: int = 120) -> str:
        return self.run("pull", remote, local, timeout=timeout)

    def content_query(self, uri: str, where: Optional[str] = None) -> str:
        cmd = f"content query --uri {uri}"
        if where:
            cmd += f" --where '{where}'"
        return self.shell(cmd, timeout=60)
