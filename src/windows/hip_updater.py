"""
hip_updater.py — Windows HIP SDK silent installer sub-agent.

Downloads the latest AMD HIP SDK installer for Windows, runs it silently,
updates environment variables, and validates the installation.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from pathlib import Path
from typing import Optional

import httpx

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig

logger = logging.getLogger(__name__)

# AMD HIP SDK download index page
_HIP_SDK_RELEASES_URL = "https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html"

# Live HIP SDK installer space. The historical repo.radeon.com/rocm/msi tree is
# retired — every path under it returns HTTP 404 — so it is never probed.
_HIP_SDK_INSTALLER_BASE = "https://download.amd.com/developer/eula/rocm-hub"

# AMD Software PRO Edition releases carrying the HIP SDK, newest first.
# Every entry below was verified live with an HTTP Range GET (bytes=0-0).
# 26.Q4, 26.Q2 and 25.Q4 return HTTP 404 and are therefore not listed — a
# wasted probe per dead quarter.
# 5 quarters x 2 suffixes = 10 probes, within _MAX_INSTALLER_PROBES.
_HIP_SDK_QUARTERS = ("26.Q3", "26.Q1", "25.Q3", "24.Q4", "24.Q3")

# Quarters whose bundle ships the 6.x-era HIP SDK. They are reachable only if
# every newer quarter is dead, and they are REFUSED at install time: a 6.x
# bundle installed over an existing 7.x SDK duplicates the component set and
# breaks the llama.cpp HIP build.
_LEGACY_6X_QUARTERS = ("24.Q4", "24.Q3")

# Filename suffix trap: recent quarters (26.Q3, 26.Q1) ship the "Win11"
# suffix only, while 25.Q3 and earlier use "Win10-Win11". Both are probed.
_HIP_SDK_QUARTER_SUFFIXES = ("Win11", "Win10-Win11")

# Hard cap on HTTP probes so a dead network cannot stall the update cycle.
_MAX_INSTALLER_PROBES = 12

# AMD's installer writes its result code to the -log file. Tolerant pattern:
# the log is a human-readable text file whose exact wording is not
# contractual, so the last "result code"-style line wins.
_INSTALLER_RESULT_CODE_RE = re.compile(r"result\s*code\s*[:=]?\s*(-?\d+)", re.IGNORECASE)

# Uninstall registry key holding the "AMD Software" package entry.
_UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

# Windows display adapter setup class GUID (GUID_DEVCLASS_DISPLAY).
_GUID_DEVCLASS_DISPLAY = "{4d36e968-e325-11ce-bfc1-08002be10318}"


class HIPUpdater:
    """Downloads and silently installs the AMD HIP SDK on Windows."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig) -> None:
        self.cfg = cfg

    def update(self) -> bool:
        """
        Run the full HIP SDK update cycle.

        Returns:
            True if a reboot is required, False otherwise.
        """
        # Step 1: Find the latest HIP SDK installer URL
        installer_url, version_str = self._find_latest_installer()
        if not installer_url:
            raise RuntimeError(
                "HIP SDK installer URL could not be resolved. Refusing to install "
                "an unverified bundle — a legacy 6.x-era SDK installed over a 7.x "
                "SDK duplicates the component set and breaks the build."
            )

        print_info(f"Latest AMD Software PRO Edition release: {version_str or 'unknown'}")

        # Step 2: Download the installer
        installer_path = self._download_installer(installer_url)
        if not installer_path:
            raise RuntimeError("HIP SDK download failed.")

        # Step 3: Run silent install
        reboot_required = self._run_silent_install(installer_path, version_str)

        # Step 4: Update environment variables
        self._update_environment_variables()

        # Step 5: Validate
        self._validate_installation()

        # Clean up temp installer
        if installer_path.exists() and not self.cfg.behavior.dry_run:
            try:
                installer_path.unlink()
            except OSError:
                pass

        return reboot_required

    # ------------------------------------------------------------------
    # Locate latest installer
    # ------------------------------------------------------------------

    def _find_latest_installer(self) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve the current AMD HIP SDK installer URL.

        The retired ``repo.radeon.com/rocm/msi`` tree (still referenced by
        ``cfg.repo.hip_sdk_download_base``) 404s on every path, so it is never
        probed. Instead the live ``download.amd.com/developer/eula/rocm-hub``
        space is probed with a one-byte Range GET (``bytes=0-0``) per
        candidate — no installer is ever fully downloaded during discovery.
        Quarters are probed newest first and both filename suffixes are tried
        per quarter, because recent quarters use the ``Win11`` suffix only
        while 25.Q3 and earlier use ``Win10-Win11``.

        Returns:
            (url, version_label) for the newest live installer.

        Raises:
            RuntimeError: if no live installer could be resolved. There is no
                legacy fallback — installing a 6.x-era bundle over a 7.x SDK
                duplicates the component set and breaks the build.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        probes = 0
        legacy_url: Optional[str] = None
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            for quarter in _HIP_SDK_QUARTERS:
                for suffix in _HIP_SDK_QUARTER_SUFFIXES:
                    if probes >= _MAX_INSTALLER_PROBES:
                        break
                    url = (
                        f"{_HIP_SDK_INSTALLER_BASE}/"
                        f"AMD-Software-PRO-Edition-{quarter}-{suffix}-For-HIP.exe"
                    )
                    probes += 1
                    try:
                        # Lightweight Range GET — never download the whole EXE.
                        resp = client.get(url, headers={"Range": "bytes=0-0"})
                    except Exception:
                        continue
                    if resp.status_code not in (200, 206):
                        continue
                    if quarter in _LEGACY_6X_QUARTERS:
                        # Live, but it ships the 6.x-era HIP SDK. Record it and
                        # keep going — it must never be installed over a 7.x SDK.
                        legacy_url = url
                        continue
                    return url, _version_label(quarter)
                if probes >= _MAX_INSTALLER_PROBES:
                    break

        if legacy_url:
            raise RuntimeError(
                "The only reachable AMD HIP SDK installer is the legacy 6.x-era "
                f"bundle {legacy_url}. Refusing to fall back to a legacy 6.x-era "
                "bundle: installing HIP SDK 6.x over an existing 7.x install "
                "duplicates the component set and breaks the llama.cpp HIP build. "
                "Install manually from "
                "https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html "
                "or retry when a newer release is published."
            )

        raise RuntimeError(
            "Could not resolve a live AMD HIP SDK installer URL from "
            f"{_HIP_SDK_INSTALLER_BASE} after {probes} probe(s). Refusing to fall "
            "back to a legacy 6.x-era bundle: installing HIP SDK 6.x over an "
            "existing 7.x install duplicates the component set and breaks the "
            "llama.cpp HIP build. Install manually from "
            "https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html "
            "or retry when the network is reachable."
        )








    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download_installer(self, url: str) -> Optional[Path]:
        """Download the HIP SDK installer EXE."""
        print_step(f"Downloading HIP SDK installer: {url}")

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would download: {url}")
            return Path(tempfile.gettempdir()) / "HIP-SDK-Installer-dry-run.exe"

        tmp_dir = Path(tempfile.gettempdir())
        filename = url.split("/")[-1]
        dest = tmp_dir / filename

        try:
            # Configure standard browser User-Agent globally for urllib downloads
            opener = urllib.request.build_opener()
            opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")]
            urllib.request.install_opener(opener)

            urllib.request.urlretrieve(url, str(dest))
            print_success(f"Downloaded to {dest}")
            return dest
        except Exception as exc:
            print_error(f"Download failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Silent install
    # ------------------------------------------------------------------

    def _run_silent_install(self, installer_path: Path, version: Optional[str]) -> bool:
        """
        Run the AMD HIP SDK installer silently using AMD's documented CLI.

        The HIP SDK installer is a GUI (WinMain) application: it ignores
        NSIS/MSI switches such as ``/S``, ``/v/qn`` and ``/norestart``, which
        is what made a GUI window pop up on the node and a human click through
        the install. AMD's documented command line is::

            -install                        silent install of packages, no output to screen
            -install -boot                  silent install with auto reboot
            -install -log PATH              write the install result code to a log file
                                            (must be a local path on the machine)
            -uninstall | -uninstall -boot | /? | /help

        Note that ``-install`` installs BOTH the bundled AMD Radeon Software PRO
        display driver and the SDK packages, and — unlike the GUI — the CLI
        cannot install a subset of the bundle. When running the installer by
        hand, the GUI components to select are:

        * wanted: HIP SDK Core, HIP Libraries, HIP Runtime Compiler, HIP Ray Tracing
        * not wanted: Visual Studio Plugin
        * optional: AMD ROCm Debugger

        The bundled AMD Display Driver is a separate manual choice in the GUI
        (Full Install / Minimal Install / Driver Only); the CLI always installs
        the driver as well, which is why the display driver version is
        captured before and after the run.

        AMD also documents ``-install -boot`` (silent install with auto
        reboot). It is deliberately NOT used here: the reboot it triggers
        happens from inside the installer, before the application has written
        its reboot handoff and registered the resume-on-boot task. The node
        would come back with neither, so the update chain (llama.cpp build)
        would never resume. The reboot is instead requested from the caller
        (this method returns True), and the application performs it only
        after the handoff file and the resume task are safely in place.

        The install result code is read from the ``-log`` file, because AMD's
        CLI may exit 0 while still requiring a reboot, and a swapped display
        driver always requires one.

        Returns:
            True if a reboot is required.
        """
        # AMD's real silent-install flags. NSIS/MSI flags are NOT used.
        # The -log path must be local to the machine.
        log_path = Path(tempfile.gettempdir()) / "amd_hip_sdk_install.log"
        # Remove a stale log so an old result code is never misread.
        try:
            log_path.unlink()
        except OSError:
            pass
        cmd = [str(installer_path), "-install", "-log", str(log_path)]

        print_step(f"Running silent install: {installer_path.name}")

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would run: {' '.join(cmd)}")
            return False

        # Display-driver guard: the CLI always installs the bundled PRO driver,
        # so capture the current state to detect a consumer-driver swap.
        package_before = _read_amd_software_package_version()
        driver_before = _read_display_driver_version()
        print_info(
            f"Pre-install display state: AMD Software package="
            f"{package_before or 'unknown'}, display driver={driver_before or 'unknown'}"
        )

        try:
            result = subprocess.run(
                cmd,
                timeout=900,  # 15 min
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("HIP SDK installer timed out after 15 minutes.")

        exit_code = result.returncode
        log_code = _read_installer_result_code(log_path)
        if log_code is not None and log_code != exit_code:
            print_info(f"Installer log result code: {log_code}")

        driver_changed = self._report_display_driver_change(package_before, driver_before)

        # Exit code 3010 = success with reboot required (MSI convention).
        # A replaced display driver also always needs a reboot to take effect.
        if exit_code == 3010 or log_code == 3010:
            print_warning("HIP SDK installed — reboot required.")
            return True
        elif exit_code == 0 and log_code in (None, 0):
            print_success(
                f"HIP SDK installer completed successfully (release: {version or 'unknown'})."
            )
            return driver_changed
        else:
            code = exit_code if exit_code != 0 else log_code
            raise RuntimeError(
                f"HIP SDK installer exited with code {code}. "
                f"Installer log: {log_path}. "
                "Check Windows Event Viewer for details."
            )

    def _report_display_driver_change(
        self,
        package_before: Optional[str],
        driver_before: Optional[str],
    ) -> bool:
        """
        Warn loudly if the automatic install replaced the consumer display driver.

        Args:
            package_before: "AMD Software" package version recorded before the install.
            driver_before: active display driver version recorded before the install.

        Returns:
            True if the active display driver version changed. A swapped
            display driver only takes effect after a reboot.
        """
        package_after = _read_amd_software_package_version()
        driver_after = _read_display_driver_version()

        if package_after and package_before and package_after != package_before:
            print_info(f"AMD Software package version: {package_before} -> {package_after}")

        if driver_before and driver_after and driver_before != driver_after:
            print_warning(
                "DISPLAY DRIVER CHANGED: "
                f"{driver_before} -> {driver_after}. "
                "The bundled AMD Radeon Software PRO display driver replaced your "
                "consumer display driver. This affects FSR and game performance — "
                "reinstall your consumer driver to restore it."
            )
            return True
        elif driver_before and driver_after and driver_before == driver_after:
            print_info(f"Display driver unchanged: {driver_after}")

        return False

    # ------------------------------------------------------------------
    # Environment variables
    # ------------------------------------------------------------------

    def _update_environment_variables(self) -> None:
        """
        Ensure HIP_PATH, ROCM_PATH, and PATH are set in the system environment.
        These are typically set by the installer itself, but we verify and patch.
        """







                # Common HIP SDK install locations — newest-first to pick the latest install.
        # ROCm 7.x is current as of HIP SDK 7.2.2 (required for latest GGML tensor formats).
        candidates = [
            Path("C:/Program Files/AMD/ROCm/7.3"),
            Path("C:/Program Files/AMD/ROCm/7.2"),
            Path("C:/Program Files/AMD/ROCm/7.1"),
            Path("C:/Program Files/AMD/ROCm/7.0"),
            Path("C:/Program Files/AMD/ROCm/6.3"),
            Path("C:/Program Files/AMD/ROCm/6.2"),
            Path("C:/Program Files/AMD/ROCm/6.1"),
            Path("C:/Program Files/AMD/ROCm"),
        ]

        hip_path: Optional[Path] = None
        for candidate in candidates:
            if (candidate / "bin" / "hipcc.exe").exists():
                hip_path = candidate
                break

        if not hip_path:
            print_warning("Could not locate HIP SDK install directory. Environment not updated.")
            return

        bin_path = str(hip_path / "bin")
        hip_path_str = str(hip_path)

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would set HIP_PATH={hip_path_str}")
            print_dry_run(f"Would set ROCM_PATH={hip_path_str}")
            print_dry_run(f"Would add to PATH: {bin_path}")
            return

        _set_system_env("HIP_PATH", hip_path_str)
        _set_system_env("ROCM_PATH", hip_path_str)
        _append_to_system_path(bin_path)
        print_success(f"Environment variables updated for HIP SDK at {hip_path}")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_installation(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: hipcc --version, hipInfo")
            return

        for exe in ("hipcc", "hipInfo"):
            try:
                result = subprocess.run(
                    [exe, "--version"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    output = (result.stdout + result.stderr).strip().split("\n")[0]
                    print_success(f"{exe}: {output[:80]}")
                    return
            except FileNotFoundError:
                continue

        print_warning("hipcc/hipInfo not found in PATH — may require restart of terminal or reboot.")


# ---------------------------------------------------------------------------
# Registry / environment helpers
# ---------------------------------------------------------------------------


def _version_label(quarter: str) -> str:
    """
    Build an accurate, verifiable label for a resolved installer URL.

    Only the AMD Software PRO Edition release quarter is asserted, because that
    is the only part of the download URL that was actually verified (HTTP
    200/206 on a one-byte Range probe). The HIP SDK component version shipped
    inside the bundle is NOT claimed — it is not observable from the URL.

    Args:
        quarter: Release quarter, e.g. "26.Q3".

    Returns:
        A short label for the resolved release.
    """
    return quarter


def _read_amd_software_package_version() -> Optional[str]:
    """
    Read the installed "AMD Software" package version from the uninstall registry.

    Looks under HKLM (both the 64-bit and 32-bit registry views) for an
    uninstall entry whose DisplayName starts with "AMD Software" and returns
    its DisplayVersion.

    Returns:
        The version string, or None if no such package is installed.
    """
    if sys.platform != "win32":
        return None

    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None

    views = []
    for flag_name in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
        flag = getattr(winreg, flag_name, None)
        if flag is not None:
            views.append(flag)
    if not views:
        views.append(0)

    for view in views:
        try:
            root = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                _UNINSTALL_KEY,
                0,
                winreg.KEY_READ | view,
            )
        except OSError:
            continue

        try:
            subkey_count = winreg.QueryInfoKey(root)[0]
            for index in range(subkey_count):
                subkey_name = winreg.EnumKey(root, index)
                try:
                    with winreg.OpenKey(root, subkey_name, 0, winreg.KEY_READ | view) as subkey:
                        display_name = str(winreg.QueryValueEx(subkey, "DisplayName")[0])
                        if not display_name.startswith("AMD Software"):
                            continue
                        try:
                            display_version = str(winreg.QueryValueEx(subkey, "DisplayVersion")[0])
                        except OSError:
                            continue
                        return display_version
                except OSError:
                    continue
        finally:
            winreg.CloseKey(root)

    return None


def _read_installer_result_code(log_path: Path) -> Optional[int]:
    """
    Read the install result code AMD's installer wrote to its ``-log`` file.

    AMD's CLI reports the install result code in the log file, and the
    process exit code alone is not sufficient: the installer can exit 0
    while still requiring a reboot (code 3010).

    Args:
        log_path: path of the ``-log`` file passed to the installer.

    Returns:
        The result code as an int, or None if the log is missing or does
        not contain a recognisable result code.
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    matches = _INSTALLER_RESULT_CODE_RE.findall(text)
    if not matches:
        return None

    try:
        return int(matches[-1])
    except ValueError:
        return None


def _read_display_driver_version() -> Optional[str]:
    """
    Read the active display adapter driver version without WMI.

    Two sources are tried, in order:

    1. The display class registry key
       ``HKLM\\SYSTEM\\CurrentControlSet\\Control\\Class\\{GUID_DEVCLASS_DISPLAY}``.
       Each adapter instance is a subkey whose ``MatchingDeviceId`` identifies
       the PCI device; the AMD adapter is the one whose id contains
       ``VEN_1002``. Its ``DriverVersion`` is the real, currently loaded
       driver version (e.g. ``31.0.21923.11000``).
    2. SetupAPI's ``SPDRP_DRIVERVERSION`` for the same adapter.

    The "AMD Software" uninstall entry is deliberately NOT used as a
    fallback: its ``DisplayVersion`` is the package version (e.g.
    ``25.8.1``), which is a different value from the display driver
    version. Conflating the two would make the driver-change check
    compare package versions instead of driver versions.

    Returns:
        The driver version string, or None if it could not be determined.
    """
    if sys.platform != "win32":
        return None

    version = _read_display_driver_version_registry()
    if version:
        return version

    return _read_display_driver_version_setupapi()


def _read_display_driver_version_registry() -> Optional[str]:
    """
    Read the AMD display driver version from the display class registry key.

    Returns:
        The driver version string, or None if the key or the AMD adapter
        entry could not be read.
    """
    if sys.platform != "win32":
        return None

    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None

    class_key = rf"SYSTEM\CurrentControlSet\Control\Class\{_GUID_DEVCLASS_DISPLAY}"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, class_key, 0, winreg.KEY_READ)
    except OSError:
        return None

    try:
        subkey_count = winreg.QueryInfoKey(root)[0]
        for index in range(subkey_count):
            try:
                subkey_name = winreg.EnumKey(root, index)
            except OSError:
                continue
            try:
                with winreg.OpenKey(root, subkey_name, 0, winreg.KEY_READ) as subkey:
                    try:
                        matching_id = str(winreg.QueryValueEx(subkey, "MatchingDeviceId")[0])
                    except OSError:
                        continue
                    if "VEN_1002" not in matching_id.upper():
                        continue
                    try:
                        driver_version = str(winreg.QueryValueEx(subkey, "DriverVersion")[0])
                    except OSError:
                        continue
                    return driver_version.strip() or None
            except OSError:
                continue
    finally:
        winreg.CloseKey(root)

    return None


def _read_display_driver_version_setupapi() -> Optional[str]:
    """
    Read the AMD display driver version via SetupAPI (ctypes, no WMI, no shell).

    Returns:
        The driver version string, or None if SetupAPI is unavailable.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:  # pragma: no cover - non-Windows
        return None

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _SP_DEVINFO_DATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint32),
            ("ClassGuid", _GUID),
            ("DevInst", ctypes.c_uint32),
            ("Reserved", ctypes.POINTER(ctypes.c_uint32)),
        ]

    DIGCF_PRESENT = 0x00000002
    SPDRP_HARDWAREID = 0x00000001
    SPDRP_DRIVERVERSION = 0x00000011
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    display_class = _GUID(
        0x4D36E968,
        0xE325,
        0x11CE,
        (ctypes.c_ubyte * 8)(0xBF, 0xC1, 0x08, 0x00, 0x2B, 0xE1, 0x03, 0x18),
    )

    try:
        setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
    except (AttributeError, OSError):  # pragma: no cover - non-Windows
        return None

    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
    ]
    setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    setupapi.SetupDiEnumDeviceInfo.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(_SP_DEVINFO_DATA),
    ]
    setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
    setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_SP_DEVINFO_DATA),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    setupapi.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    def _read_property(handle, dev_info, prop):
        """Read a string device registry property, or None."""
        required = wintypes.DWORD(0)
        reg_type = wintypes.DWORD(0)
        # First call only asks for the required size. Windows answers with
        # FALSE/ERROR_INSUFFICIENT_BUFFER here but still fills `required`,
        # so the return value must not be used as the failure signal.
        setupapi.SetupDiGetDeviceRegistryPropertyW(
            handle,
            ctypes.byref(dev_info),
            prop,
            ctypes.byref(reg_type),
            None,
            0,
            ctypes.byref(required),
        )
        if required.value == 0:
            return None
        # `required` is a byte count; create_unicode_buffer wants characters.
        buffer = ctypes.create_unicode_buffer(required.value // 2 + 1)
        ok = setupapi.SetupDiGetDeviceRegistryPropertyW(
            handle,
            ctypes.byref(dev_info),
            prop,
            ctypes.byref(reg_type),
            buffer,
            required.value,
            ctypes.byref(required),
        )
        if not ok:
            return None
        return buffer.value.strip() or None

    handle = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(display_class), None, None, DIGCF_PRESENT
    )
    if not handle or handle == INVALID_HANDLE_VALUE:
        return None

    fallback = None
    try:
        index = 0
        while True:
            device_info = _SP_DEVINFO_DATA()
            device_info.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
            if not setupapi.SetupDiEnumDeviceInfo(handle, index, ctypes.byref(device_info)):
                break
            index += 1

            hardware_ids = _read_property(handle, device_info, SPDRP_HARDWAREID) or ""
            driver_version = _read_property(handle, device_info, SPDRP_DRIVERVERSION)
            if not driver_version:
                continue
            if "VEN_1002" in hardware_ids.upper():
                return driver_version
            if fallback is None:
                fallback = driver_version
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(handle)

    return fallback


def _set_system_env(name: str, value: str) -> None:
    """Write a system environment variable to the Windows registry."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        logger.debug("Set system env %s = %s", name, value)
    except OSError as exc:
        logger.warning("Could not set %s in registry: %s", name, exc)


def _append_to_system_path(new_dir: str) -> None:
    """Add a directory to the system PATH if not already present."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
        )
        current_path, _ = winreg.QueryValueEx(key, "Path")
        paths = [p.strip() for p in current_path.split(";") if p.strip()]
        if new_dir not in paths:
            paths.append(new_dir)
            updated = ";".join(paths)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated)
            logger.debug("Appended %s to system PATH", new_dir)
        winreg.CloseKey(key)
    except OSError as exc:
        logger.warning("Could not update system PATH: %s", exc)
