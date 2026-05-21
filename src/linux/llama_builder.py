"""
llama_builder.py (Linux) — Builds llama.cpp with HIP/ROCm backend on Linux.

Clones or pulls latest llama.cpp, configures CMake with GGML_HIP=ON and
the detected AMDGPU_TARGETS, builds with all available cores, then installs
the binaries to the configured path.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import platform
from pathlib import Path
from typing import List

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig
from src.gpu_detect import get_compute_tier
from src.privilege import get_linux_sudo_prefix

logger = logging.getLogger(__name__)

_VULKAN_HEADER_CANDIDATES = (
    Path("/usr/include/vulkan/vulkan.h"),
    Path("/usr/local/include/vulkan/vulkan.h"),
)

_SPIRV_HEADER_CANDIDATES = (
    Path("/usr/include/spirv/unified1/spirv.hpp"),
    Path("/usr/local/include/spirv/unified1/spirv.hpp"),
)


class LlamaBuilderLinux:
    """Clones, builds, and installs llama.cpp on Linux with AMD HIP."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig, gpu_targets: List[str]) -> None:
        self.cfg = cfg
        self.gpu_targets = gpu_targets
        self.source_dir = Path(cfg.paths.llama_cpp_source).expanduser()
        self.install_dir = Path(cfg.paths.llama_cpp_install_linux)
        self.build_dir = self.source_dir / "build-hip"

    def build_and_install(self) -> None:
        """Full clone → cmake configure → build → install cycle."""
        self._preflight_check()
        self._clone_or_pull()
        self._configure_cmake()
        self._build()
        self._install()
        self._validate()

    # ------------------------------------------------------------------
    # Pre-flight
    # ------------------------------------------------------------------

    def _preflight_check(self) -> None:
        """Ensure cmake, ninja, and hipcc are available."""
        tier = get_compute_tier(self.gpu_targets)
        use_hip = bool(shutil.which("hipcc"))
        planned_ninja_install = False

        if not use_hip:
            if tier == 1:
                raise RuntimeError(
                    "hipcc not found. Tier 1 hardware REQUIRES the ROCm HIP SDK. "
                    "Install it and ensure it is on PATH before proceeding."
                )

            print_warning("hipcc not found. Tier 2 hardware detected — falling back to Vulkan.")

        missing_requirements = _detect_missing_linux_requirements(use_hip=use_hip)
        if missing_requirements:
            planned_ninja_install = _install_linux_build_prerequisites(
                missing_requirements,
                use_hip=use_hip,
                dry_run=self.cfg.behavior.dry_run,
            )

        if self.cfg.behavior.dry_run:
            self._use_ninja = bool(shutil.which("ninja")) or planned_ninja_install
        else:
            remaining_requirements = _detect_missing_linux_requirements(use_hip=use_hip)
            if remaining_requirements:
                raise RuntimeError(
                    "Required Linux build prerequisites are still missing after the automatic "
                    f"install attempt: {_format_missing_linux_requirements(remaining_requirements)}"
                )
            self._use_ninja = bool(shutil.which("ninja"))

        if not self._use_ninja:
            print_warning("ninja not found — falling back to make (slower build).")
        else:
            print_info("Using Ninja build system for faster compilation.")

        if self.cfg.behavior.dry_run:
            print_dry_run("Pre-flight checks passed (dry-run).")

    # ------------------------------------------------------------------
    # Clone / pull
    # ------------------------------------------------------------------

    def _clone_or_pull(self) -> None:
        # Linux uses AMD's ROCm fork per AMD documentation
        repo_url = self.cfg.repo.llama_cpp_repo

        if self.cfg.behavior.dry_run:
            if self.source_dir.exists():
                print_dry_run(f"Would pull latest: git -C {self.source_dir} pull")
            else:
                print_dry_run(f"Would clone {repo_url} → {self.source_dir}")
            return

        if (self.source_dir / ".git").exists():
            print_step(f"Pulling latest llama.cpp in {self.source_dir}...")
            _run(["git", "-C", str(self.source_dir), "pull", "--ff-only"])
            print_success("Repository updated.")
        else:
            print_step(f"Cloning llama.cpp from {repo_url}...")
            self.source_dir.parent.mkdir(parents=True, exist_ok=True)
            _run(["git", "clone", "--depth=1", repo_url, str(self.source_dir)])
            print_success(f"Cloned to {self.source_dir}")

    # ------------------------------------------------------------------
    # CMake configure
    # ------------------------------------------------------------------

    def _configure_cmake(self) -> None:
        targets_str = ";".join(self.gpu_targets)
        use_hip = bool(shutil.which("hipcc"))

        cmake_args = [
            "cmake",
            "-S", str(self.source_dir),
            "-B", str(self.build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={self.install_dir}",
        ]

        if use_hip:
            cmake_args += [
                f"-DAMDGPU_TARGETS={targets_str}",
                "-DGGML_HIP=ON",
                "-DGGML_HIP_ROCWMMA_FATTN=ON",
                "-DLLAMA_CURL=ON",   # AMD docs require this flag
            ]
        else:
            cmake_args.append("-DGGML_VULKAN=ON")
            print_info("Enabling Vulkan backend (HIP fallback for mobile/edge targets).")

        if self._use_ninja:
            cmake_args += ["-GNinja"]

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would configure: {' '.join(cmake_args)}")
            return

        print_step(f"Configuring CMake (targets: {targets_str})...")
        self.build_dir.mkdir(parents=True, exist_ok=True)
        _run(cmake_args)
        print_success("CMake configuration complete.")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        n_jobs = os.cpu_count() or 4

        env = os.environ.copy()

        # AMD docs: set HIPCXX and HIP_PATH via hipconfig before cmake build
        if shutil.which("hipconfig"):
            try:
                hipcxx_dir = subprocess.check_output(
                    ["hipconfig", "-l"], text=True
                ).strip()
                hip_path = subprocess.check_output(
                    ["hipconfig", "-R"], text=True
                ).strip()
                env["HIPCXX"] = f"{hipcxx_dir}/clang"
                env["HIP_PATH"] = hip_path
                print_info(f"HIPCXX={env['HIPCXX']}  HIP_PATH={hip_path}")
            except Exception as exc:
                print_warning(f"hipconfig query failed: {exc} — using default env")

        if get_compute_tier(self.gpu_targets) == 2:
            print_info("Tier 2 Mobile/Edge architecture detected. Injecting LLAMA_HIP_UMA=1.")
            env["LLAMA_HIP_UMA"] = "1"

        if self._use_ninja:
            build_cmd = ["ninja", "-C", str(self.build_dir), f"-j{n_jobs}"]
        else:
            build_cmd = [
                "cmake", "--build", str(self.build_dir),
                "--config", "Release",
                f"-j{n_jobs}",
            ]

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would build with {n_jobs} cores: {' '.join(build_cmd)}")
            return

        print_step(f"Building llama.cpp with {n_jobs} cores...")
        _run(build_cmd, env=env)
        print_success("Build complete.")

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _install(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would install binaries to {self.install_dir}")
            return

        install_cmd = ["cmake", "--install", str(self.build_dir), "--prefix", str(self.install_dir)]
        install_requires_privilege = _path_requires_privilege(self.install_dir)
        print_step(f"Installing binaries to {self.install_dir}...")
        _ensure_directory(self.install_dir, privileged=install_requires_privilege)
        _run_with_optional_privilege(install_cmd, privileged=install_requires_privilege)
        print_success(f"Installed to {self.install_dir}")

        # Symlink the binaries into /usr/local/bin for convenience
        bin_dir = self.install_dir / "bin"
        if bin_dir.exists():
            symlink_dir = Path("/usr/local/bin")
            _symlink_binaries(
                bin_dir,
                symlink_dir,
                privileged=_path_requires_privilege(symlink_dir),
            )

        mirrored_bin_dir = _mirror_install_bin_tree(bin_dir, self.source_dir / "bin")
        if mirrored_bin_dir:
            print_info(f"Mirrored installed binaries into {mirrored_bin_dir}")

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: llama-cli --version")
            return

        for binary in ("llama-cli", "llama-server"):
            binary_path = self.install_dir / "bin" / binary
            if binary_path.exists():
                try:
                    result = subprocess.run(
                        [str(binary_path), "--version"],
                        capture_output=True, text=True, timeout=10
                    )
                    output = (result.stdout + result.stderr).strip().split("\n")[0]
                    print_success(f"{binary}: {output[:80]}")
                    return
                except Exception as exc:
                    print_warning(f"Could not run {binary}: {exc}")

        print_warning("Could not validate llama.cpp binary — check installation manually.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
    """Run a command, streaming output to the terminal. Raises on failure."""
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=timeout, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def _run_privileged(cmd: list[str], timeout: int = 3600, env: dict | None = None) -> None:
    """Run a command through sudo when Linux install paths require elevation."""
    full_cmd = get_linux_sudo_prefix() + cmd
    logger.debug("Running privileged command: %s", " ".join(full_cmd))
    result = subprocess.run(full_cmd, timeout=timeout, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(full_cmd)}")


def _run_with_optional_privilege(
    cmd: list[str],
    *,
    privileged: bool,
    timeout: int = 3600,
    env: dict | None = None,
) -> None:
    if privileged:
        _run_privileged(cmd, timeout=timeout, env=env)
    else:
        _run(cmd, timeout=timeout, env=env)


def _path_requires_privilege(path: Path) -> bool:
    """Return True when the current user cannot write the path or its nearest existing parent."""
    candidate = path
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return not os.access(candidate, os.W_OK)


def _ensure_directory(path: Path, *, privileged: bool) -> None:
    """Create a directory tree either directly or via sudo."""
    if privileged:
        _run_privileged(["mkdir", "-p", str(path)])
    else:
        path.mkdir(parents=True, exist_ok=True)


def _mirror_install_bin_tree(install_bin: Path, source_bin: Path) -> Path | None:
    """Copy the canonical install bin tree into the source-root bin directory."""
    if not install_bin.exists():
        return None

    if install_bin.resolve(strict=False) == source_bin.resolve(strict=False):
        return None

    if source_bin.is_symlink() or source_bin.is_file():
        source_bin.unlink()
    elif source_bin.exists():
        shutil.rmtree(source_bin)

    shutil.copytree(install_bin, source_bin)
    return source_bin


def _symlink_binaries(src_dir: Path, dest_dir: Path, *, privileged: bool = False) -> None:
    """Create symlinks in dest_dir pointing to binaries in src_dir."""
    if privileged:
        _run_privileged(["mkdir", "-p", str(dest_dir)])

    for binary in src_dir.iterdir():
        if binary.is_file() and os.access(str(binary), os.X_OK):
            link = dest_dir / binary.name
            try:
                if privileged:
                    _run_privileged(["ln", "-sfn", str(binary), str(link)])
                else:
                    if link.exists() or link.is_symlink():
                        link.unlink()
                    link.symlink_to(binary)
                logger.debug("Symlinked %s → %s", binary, link)
            except OSError as exc:
                logger.warning("Could not symlink %s: %s", binary, exc)


def _detect_distro() -> str:
    """Return a lowercase distro identifier string."""
    try:
        info = platform.freedesktop_os_release()
        return (info.get("ID", "") + " " + info.get("ID_LIKE", "")).lower().strip()
    except AttributeError:
        try:
            with open("/etc/os-release", encoding="utf-8") as fh:
                return fh.read().lower()
        except OSError:
            return ""


def _is_debian_based(distro: str) -> bool:
    return any(name in distro for name in ("ubuntu", "debian", "mint", "pop"))


def _is_arch_based(distro: str) -> bool:
    return any(name in distro for name in ("arch", "steamos", "manjaro", "endeavouros"))


def _is_steamos(distro: str) -> bool:
    return "steamos" in distro


def _is_fedora_based(distro: str) -> bool:
    return any(name in distro for name in ("fedora", "rhel", "rocky", "alma", "centos"))


def _find_first_available_command(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None


def _has_vulkan_headers() -> bool:
    return any(path.exists() for path in _VULKAN_HEADER_CANDIDATES)


def _has_spirv_headers() -> bool:
    return any(path.exists() for path in _SPIRV_HEADER_CANDIDATES)


def _detect_missing_linux_requirements(*, use_hip: bool) -> list[str]:
    missing: list[str] = []

    if not shutil.which("cmake"):
        missing.append("cmake")
    if not shutil.which("git"):
        missing.append("git")
    if not _find_first_available_command(("cc", "gcc", "clang")):
        missing.append("C compiler")
    if not _find_first_available_command(("c++", "g++", "clang++")):
        missing.append("C++ compiler")
    if not shutil.which("ninja") and not shutil.which("make"):
        missing.append("build tool")

    if not use_hip:
        if not shutil.which("glslc"):
            missing.append("glslc")
        if not _has_vulkan_headers():
            missing.append("Vulkan headers")
        if not _has_spirv_headers():
            missing.append("SPIRV-Headers")

    return missing


def _build_linux_dependency_install_plan(distro: str, *, use_hip: bool) -> tuple[str, list[list[str]], bool] | None:
    if _is_debian_based(distro) and shutil.which("apt-get"):
        packages = ["build-essential", "cmake", "git", "ninja-build"]
        if not use_hip:
            packages.extend(["libvulkan-dev", "glslc", "spirv-headers"])
        return (
            "apt-get",
            [
                ["apt-get", "update"],
                ["apt-get", "install", "-y", "--no-install-recommends", *_dedupe_preserve_order(packages)],
            ],
            True,
        )

    if _is_arch_based(distro) and shutil.which("pacman"):
        packages = ["base-devel", "cmake", "git", "ninja"]
        if not use_hip:
            packages.extend(["shaderc", "spirv-headers", "vulkan-headers"])
        return (
            "pacman",
            [["pacman", "-S", "--needed", "--noconfirm", *_dedupe_preserve_order(packages)]],
            True,
        )

    dnf_binary = _find_first_available_command(("dnf5", "dnf", "yum"))
    if _is_fedora_based(distro) and dnf_binary:
        packages = ["cmake", "git", "gcc-c++", "make", "ninja-build"]
        if not use_hip:
            packages.extend(["vulkan-loader-devel", "shaderc", "spirv-headers-devel"])
        return (
            dnf_binary,
            [[dnf_binary, "install", "-y", *_dedupe_preserve_order(packages)]],
            True,
        )

    return None


def _install_linux_build_prerequisites(
    missing_requirements: list[str],
    *,
    use_hip: bool,
    dry_run: bool,
) -> bool:
    distro = _detect_distro()
    plan = _build_linux_dependency_install_plan(distro, use_hip=use_hip)
    formatted_missing = _format_missing_linux_requirements(missing_requirements)

    if not plan:
        base_hint = "cmake, git, a C/C++ toolchain, and either ninja or make"
        vulkan_hint = f"{base_hint}, plus glslc, Vulkan headers, and SPIRV-Headers"
        raise RuntimeError(
            "Could not determine how to install missing Linux build prerequisites "
            f"({formatted_missing}) on distro '{distro or 'unknown'}'. Install "
            f"{'the Vulkan fallback packages manually' if not use_hip else 'the required build packages manually'} "
            f"({vulkan_hint if not use_hip else base_hint}) before proceeding."
        )

    package_manager, commands, installs_ninja = plan
    print_step(
        "Missing Linux build prerequisites detected "
        f"({formatted_missing}). Installing them with {package_manager}..."
    )

    steamos = _is_steamos(distro)

    if dry_run:
        if steamos:
            print_dry_run("Would unlock SteamOS read-only filesystem: steamos-readonly disable")
        for command in commands:
            print_dry_run(f"Would install Linux build prerequisites: {' '.join(command)}")
        if steamos:
            print_dry_run("Would re-lock SteamOS filesystem: steamos-readonly enable")
        return installs_ninja

    env = os.environ.copy()
    if package_manager == "apt-get":
        env["DEBIAN_FRONTEND"] = "noninteractive"

    if steamos:
        print_step("SteamOS detected — temporarily disabling read-only filesystem...")
        _run_privileged(["steamos-readonly", "disable"])

    try:
        for command in commands:
            _run_privileged(command, env=env)
    finally:
        if steamos:
            _run_privileged(["steamos-readonly", "enable"])
            print_info("SteamOS filesystem re-locked (read-only restored).")

    print_success("Linux build prerequisites installed.")
    return installs_ninja


def _format_missing_linux_requirements(missing_requirements: list[str]) -> str:
    return ", ".join(missing_requirements)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
