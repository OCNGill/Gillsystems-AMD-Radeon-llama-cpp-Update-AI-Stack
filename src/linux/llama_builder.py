"""
llama_builder.py (Linux) — Builds llama.cpp with HIP/ROCm backend on Linux.

Clones or pulls latest llama.cpp, configures CMake with GGML_HIP=ON and
the detected AMDGPU_TARGETS, builds with all available cores, then installs
the binaries to the configured path.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig
from src.gpu_detect import get_compute_tier
from src.privilege import get_linux_sudo_prefix

logger = logging.getLogger(__name__)

_VULKAN_HEADER_CANDIDATES = (
    Path("/usr/include/vulkan/vulkan.h"),
    Path("/usr/local/include/vulkan/vulkan.h"),
)

# Backend shared objects that must exist in the install tree for a GPU build
# to be considered real. A CPU-only build never installs these.
_HIP_BACKEND_ARTIFACT_PATTERN = "lib/libggml-hip.so*"
_VULKAN_BACKEND_ARTIFACT_PATTERN = "lib/libggml-vulkan.so*"

# A device line that names a real GPU backend. "CPU" alone is not enough.
_GPU_DEVICE_PATTERN = re.compile(r"\b(ROCm|Vulkan|AMD|Radeon)\b", re.IGNORECASE)

# ROCm SDK discovery roots. A distro ROCm (/usr) must never win over an SDK.
_ROCM_DEFAULT_SDK_ROOT = Path("/opt/rocm")
_ROCM_SDK_SEARCH_DIR = Path("/opt")
_ROCM_SDK_VERSIONED_PREFIX = "rocm-"


@dataclass
class RocmToolchain:
    """The ROCm toolchain the build will actually use.

    ``sdk_coherent`` is True when the toolchain comes from a real ROCm SDK
    install (its own ``hipconfig`` plus its own LLVM compiler), so the
    compile-time headers/compiler and the deployed ROCm runtime are the same
    generation. It is False when the distro ROCm (e.g. Ubuntu's ROCm 7.1 under
    /usr) was used instead, which is the classic compile/runtime skew.
    """

    root: Optional[Path] = None
    hip_path: Optional[str] = None
    hipcxx: Optional[str] = None
    hip_compiler: Optional[str] = None
    sdk_coherent: bool = False
    source: str = "none"

_VULKAN_LOADER_LIBRARY_CANDIDATES = (
    Path("/usr/lib/libvulkan.so"),
    Path("/usr/lib64/libvulkan.so"),
    Path("/usr/local/lib/libvulkan.so"),
    Path("/usr/local/lib64/libvulkan.so"),
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
        self.source_dir = cfg.paths.resolve_llama_cpp_source()
        self.install_dir = cfg.paths.resolve_llama_cpp_install_linux()
        # Computed once at construction; all methods use self.use_hip for consistency.
        self.use_hip = bool(shutil.which("hipcc"))
        # Name the build directory by the actual backend so HIP and Vulkan builds
        # never share the same CMakeCache and pollute each other's object files.
        self.build_dir = self.source_dir / ("build-hip" if self.use_hip else "build-vulkan")
        # Resolved lazily on first use so the ROCm SDK is discovered once and
        # the same toolchain is used for configure, build and validation.
        self._rocm_toolchain_cache: Optional[RocmToolchain] = None

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
        use_hip = self.use_hip
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
        # Uses the mainstream ggml-org fork (configured via llama_cpp_repo in config)
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
        use_hip = self.use_hip

        cmake_args = [
            "cmake",
            "-S", str(self.source_dir),
            "-B", str(self.build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={self.install_dir}",
        ]

        # The repair re-configure must use exactly the same arguments as the
        # first attempt, so they are kept in one list.
        hip_cmake_args: list[str] = []

        if use_hip:
            toolchain = self._rocm_toolchain()
            hip_cmake_args = [
                "cmake",
                "-S", str(self.source_dir),
                "-B", str(self.build_dir),
                "-DCMAKE_BUILD_TYPE=Release",
                f"-DCMAKE_INSTALL_PREFIX={self.install_dir}",
                f"-DAMDGPU_TARGETS={targets_str}",
                "-DGGML_HIP=ON",
                "-DGGML_HIP_ROCWMMA_FATTN=OFF",
                "-DLLAMA_CURL=ON",   # AMD docs require this flag
            ]
            if toolchain.sdk_coherent and toolchain.root is not None:
                # Compile against the same ROCm generation that will be
                # deployed at runtime. Without these the build can silently
                # use the distro ROCm (e.g. 7.1 under /usr) while the machine
                # loads the AMD SDK runtime (e.g. 7.2.4 under /opt/rocm-7.2.4).
                hip_cmake_args += [
                    f"-DROCM_PATH={toolchain.root}",
                    f"-DCMAKE_HIP_COMPILER={toolchain.hip_compiler}",
                ]
            cmake_args = list(hip_cmake_args)
        else:
            cmake_args += ["-DGGML_VULKAN=ON", "-DGGML_HIP=OFF"]
            print_info("Enabling Vulkan backend (HIP fallback for mobile/edge targets).")

        if self._use_ninja:
            cmake_args += ["-GNinja"]
            if use_hip:
                hip_cmake_args += ["-GNinja"]

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would configure: {' '.join(cmake_args)}")
            return

        print_step(f"Configuring CMake (targets: {targets_str})...")
        self.build_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.build_dir / "CMakeCache.txt"
        if cache_file.exists():
            cache_file.unlink()
        _run(cmake_args)
        print_success("CMake configuration complete.")

        # A ROCm/HIP SDK upgrade swaps the compiler (e.g. 7.1 -> 7.2). CMake
        # reacts by deleting its own cache and re-running configure, and that
        # re-configure can silently drop -DGGML_HIP=ON. The result is a
        # CPU-only build that still "succeeds" and still passes every
        # --version check. Read the cache back and repair it.
        if use_hip:
            state = self._hip_backend_cache_state()
            if state != "on":
                print_warning(
                    "CMake cache does not report GGML_HIP=ON after configure "
                    f"(cache state: {state}). Re-configuring with HIP explicitly "
                    "enabled so the GPU backend is actually built."
                )
                if cache_file.exists():
                    cache_file.unlink()
                _run(hip_cmake_args)
                state = self._hip_backend_cache_state()
                if state != "on":
                    raise RuntimeError(
                        "CMake cache still does not report GGML_HIP=ON after a "
                        f"re-configure with HIP explicitly enabled (cache state: {state}). "
                        "The HIP configure was lost and the build would be CPU-only. "
                        "Refusing to build a CPU-only llama.cpp."
                    )
                print_success("Re-configured with HIP enabled; GGML_HIP=ON is in the cache.")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _hip_backend_cache_state(self) -> str:
        """Tri-state read of this build's CMake cache: 'on', 'off' or 'unknown'."""
        return _hip_cache_state(self.build_dir)

    def _rocm_toolchain(self) -> RocmToolchain:
        """Resolve (once) and report the ROCm toolchain used for this build.

        A distro ROCm on PATH (e.g. Ubuntu's ROCm 7.1 under /usr) can differ
        from the deployed AMD SDK runtime (e.g. 7.2.4 under /opt/rocm-7.2.4).
        Preferring a real SDK root keeps compile-time and runtime coherent.
        """
        if self._rocm_toolchain_cache is None:
            self._rocm_toolchain_cache = _resolve_rocm_toolchain()
            toolchain = self._rocm_toolchain_cache
            print_info(
                f"ROCm toolchain: root={toolchain.root or 'unknown'}  "
                f"HIPCXX={toolchain.hipcxx or 'unknown'}  "
                f"SDK-coherent={'yes' if toolchain.sdk_coherent else 'no'}  "
                f"(source: {toolchain.source})"
            )
        return self._rocm_toolchain_cache

    def _hip_runtime_env(self) -> dict:
        """Environment for HIP runtime checks: load the resolved ROCm runtime.

        The device enumeration must run against the same ROCm generation the
        binary was linked against, otherwise the check would probe a different
        runtime than the one the updater will actually use.
        """
        env = os.environ.copy()
        if not self.use_hip:
            return env

        toolchain = self._rocm_toolchain()
        lib_dirs: list[str] = []
        for base in (toolchain.root, Path(toolchain.hip_path) if toolchain.hip_path else None):
            if base is None:
                continue
            lib_dir = str(base / "lib")
            if lib_dir not in lib_dirs:
                lib_dirs.append(lib_dir)

        existing = env.get("LD_LIBRARY_PATH", "")
        prefix = os.pathsep.join(lib_dirs)
        if prefix and existing:
            env["LD_LIBRARY_PATH"] = f"{prefix}{os.pathsep}{existing}"
        elif prefix:
            env["LD_LIBRARY_PATH"] = prefix
        if toolchain.hip_path:
            env["HIP_PATH"] = toolchain.hip_path
        return env

    def _build(self) -> None:
        n_jobs = os.cpu_count() or 4

        env = os.environ.copy()

        # AMD docs: set HIPCXX and HIP_PATH via hipconfig before cmake build.
        # When a ROCm SDK is available we use the SDK's own hipconfig so the
        # compiler and the deployed ROCm runtime are the same generation.
        if self.use_hip:
            toolchain = self._rocm_toolchain()
            if toolchain.hipcxx:
                env["HIPCXX"] = toolchain.hipcxx
            if toolchain.hip_path:
                env["HIP_PATH"] = toolchain.hip_path
            if not toolchain.sdk_coherent:
                print_warning(
                    "No ROCm SDK root found — falling back to the PATH hipconfig "
                    f"(HIPCXX={env.get('HIPCXX')}, HIP_PATH={env.get('HIP_PATH')}). "
                    "The build may not be SDK-coherent with the deployed ROCm runtime."
                )

        if self.use_hip and get_compute_tier(self.gpu_targets) == 2:
            print_info("Tier 2 Mobile/Edge + HIP architecture detected. Injecting LLAMA_HIP_UMA=1.")
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

        # Shared binaries dir (used by lib mirroring, PATH symlinks, and mirroring)
        bin_dir = self.install_dir / "bin"

        # Newer llama.cpp installs shared libs to lib/ but binaries lack an rpath to ../lib.
        # Mirror libs into bin/ so every launcher works without LD_LIBRARY_PATH plumbing.
        lib_dir = self.install_dir / "lib"
        if lib_dir.exists() and bin_dir.exists():
            for lib in lib_dir.glob("*.so*"):
                link = bin_dir / lib.name
                if link.is_symlink() or link.exists():
                    link.unlink()
                try:
                    link.symlink_to(lib)
                except OSError as exc:
                    print_warning(f"Could not link {lib.name} into bin/: {exc}")

        # Symlink the binaries into /usr/local/bin for convenience
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

    def _verify_hip_backend_artifact(self) -> None:
        """Assert the HIP backend shared object exists in the install tree."""
        expected = self.install_dir / "lib" / "libggml-hip.so*"
        try:
            found = list((self.install_dir / "lib").glob("libggml-hip.so*"))
        except OSError:
            found = []
        if not found:
            raise RuntimeError(
                "The HIP backend library was not found in the install tree "
                f"(expected {expected}). The build did not produce a HIP "
                "backend and would run CPU-only. Refusing to report a "
                "successful update."
            )
        print_success(f"HIP backend artifact present: {found[0].name}")

    def _verify_gpu_backend(self, runtime_env: dict) -> bool:
        """Prove a real GPU backend registers with the installed binaries.

        A CPU-only build passes every --version check, so the only honest test
        is to ask the binary which devices it can see and require a non-CPU
        one. When the binary cannot enumerate devices we fall back to
        requiring the backend shared object to be present in the install tree.
        """
        cli = self.install_dir / "bin" / "llama-cli"
        if cli.exists():
            try:
                result = subprocess.run(
                    [str(cli), "--list-devices"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=runtime_env,
                )
            except Exception as exc:
                print_warning(f"Could not enumerate devices via llama-cli: {exc}")
                result = None
            if result is not None and result.returncode == 0:
                output = (result.stdout or "") + (result.stderr or "")
                if _GPU_DEVICE_PATTERN.search(output):
                    print_success("GPU device enumerated via llama-cli --list-devices.")
                    return True
                print_warning(
                    "llama-cli --list-devices reported no ROCm/Vulkan device — "
                    "the build looks CPU-only."
                )
                return False
            if result is not None:
                print_warning(
                    "llama-cli --list-devices is not supported by this build; "
                    "falling back to the backend library check."
                )

        # Fallback: the backend shared object must be installed.
        for pattern in self._backend_artifact_patterns():
            try:
                matches = list(self.install_dir.glob(pattern))
            except OSError:
                matches = []
            if matches:
                print_success(f"GPU backend library present in the install tree: {matches[0].name}")
                return True

        print_warning(
            "No GPU device could be enumerated and no GPU backend library is "
            "present in the install tree."
        )
        return False

    def _backend_artifact_patterns(self) -> List[str]:
        """Glob patterns (relative to the install dir) for the backend .so."""
        if self.use_hip:
            return [_HIP_BACKEND_ARTIFACT_PATTERN]
        return [_VULKAN_BACKEND_ARTIFACT_PATTERN, "lib/*vulkan*.so*"]

    def _validate(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: llama-cli --version")
            return

        runtime_env = self._hip_runtime_env()

        validated: list[str] = []
        for binary in ("llama-cli", "llama-server"):
            binary_path = self.install_dir / "bin" / binary
            if binary_path.exists():
                try:
                    result = subprocess.run(
                        [str(binary_path), "--version"],
                        capture_output=True, text=True, timeout=10, env=runtime_env
                    )
                    output = (result.stdout + result.stderr).strip().split("\n")[0]
                    print_success(f"{binary}: {output[:80]}")
                    validated.append(binary)
                except Exception as exc:
                    print_warning(f"Could not run {binary}: {exc}")
            else:
                print_warning(f"Expected binary not found: {binary_path}")

        if not validated:
            print_warning("Could not validate any llama.cpp binaries — check installation manually.")

        # A CPU-only build installs no HIP backend. Assert it is really there
        # instead of trusting that the configure asked for it.
        if self.use_hip:
            self._verify_hip_backend_artifact()

        # --version proves the binary runs, not that it has a GPU backend.
        # A CPU-only build passes every --version check, so require positive
        # evidence that a real GPU device registers.
        if not self._verify_gpu_backend(runtime_env):
            raise RuntimeError(
                "llama.cpp was installed but no GPU device could be verified. "
                "The build is CPU-only or the GPU backend failed to register. "
                "Refusing to report a successful update."
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hip_cache_state(build_dir: Path) -> str:
    """Return "on", "off" or "unknown" for the CMake cache's GGML_HIP entry.

    "unknown" means CMake never wrote a cache we can read (or the entry is
    absent), so there is nothing to enforce. "unknown" is NEVER treated as
    "off" — it just means we cannot prove HIP is enabled.
    """
    cache_file = build_dir / "CMakeCache.txt"
    try:
        content = cache_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "unknown"
    match = re.search(r"^GGML_HIP:BOOL=(\w+)", content, re.MULTILINE)
    if not match:
        return "unknown"
    return "on" if match.group(1).upper() == "ON" else "off"


def _is_rocm_sdk_root(root: Path) -> bool:
    """True when *root* is a real ROCm SDK install, not a distro ROCm.

    A ROCm SDK ships its own LLVM toolchain and its own hipconfig:
    ``<root>/lib/llvm/bin/clang++`` and ``<root>/bin/hipconfig``.
    Ubuntu's packaged ROCm (e.g. 7.1 under /usr) does not match this shape,
    which is exactly why it must never win over an SDK root.
    """
    try:
        if not root.is_dir():
            return False
    except OSError:
        return False
    return (root / "lib" / "llvm" / "bin" / "clang++").exists() and (root / "bin" / "hipconfig").exists()


def _rocm_version_sort_key(name: str) -> tuple[int, ...]:
    """Sort key for ROCm version directories like 'rocm-7.2.4'."""
    digits: list[int] = []
    for chunk in name.replace("-", ".").split("."):
        digits.append(int(chunk) if chunk.isdigit() else 0)
    return tuple(digits)


def _rocm_sdk_candidates(
    search_dir: Optional[Path] = None,
    default_root: Optional[Path] = None,
) -> List[Path]:
    """ROCm root candidates in priority order.

    1. ``$HIP_PATH`` when it already looks like an SDK install.
    2. ``/opt/rocm`` (usually a symlink to the versioned SDK).
    3. ``/opt/rocm-<version>`` directories, highest version first.

    A distro ROCm root such as /usr is deliberately absent: it must never be
    preferred over an available SDK root.
    """
    candidates: List[Path] = []

    hip_path_env = os.environ.get("HIP_PATH")
    if hip_path_env:
        hip_path_root = Path(hip_path_env)
        if _is_rocm_sdk_root(hip_path_root):
            candidates.append(hip_path_root)

    candidates.append(default_root if default_root is not None else _ROCM_DEFAULT_SDK_ROOT)

    search_root = search_dir if search_dir is not None else _ROCM_SDK_SEARCH_DIR
    try:
        versioned = [
            entry
            for entry in search_root.iterdir()
            if entry.is_dir() and entry.name.startswith(_ROCM_SDK_VERSIONED_PREFIX)
        ]
    except OSError:
        versioned = []
    versioned.sort(key=lambda p: _rocm_version_sort_key(p.name), reverse=True)
    candidates.extend(versioned)

    return candidates


def _hipconfig_query(hipconfig: str, flag: str) -> str:
    """Run ``hipconfig <flag>`` and return its stripped output ('' on error)."""
    try:
        output = subprocess.check_output([hipconfig, flag], text=True)
    except Exception:
        return ""
    return output.strip()


def _resolve_rocm_toolchain(
    search_dir: Optional[Path] = None,
    default_root: Optional[Path] = None,
) -> RocmToolchain:
    """Resolve the ROCm SDK root, HIP_PATH and HIPCXX to build against.

    Prefers a real ROCm SDK over the distro ROCm that happens to be first on
    PATH, so the compile-time compiler and the deployed ROCm runtime are the
    same generation. Falls back to the PATH ``hipconfig`` when no SDK root is
    available (still functional, just not SDK-coherent).
    """
    for root in _rocm_sdk_candidates(search_dir=search_dir, default_root=default_root):
        if not _is_rocm_sdk_root(root):
            continue
        hipconfig = str(root / "bin" / "hipconfig")
        # Use the SDK's OWN hipconfig, never the one that may be first on PATH.
        hip_path = _hipconfig_query(hipconfig, "-R") or str(root)
        hipcxx_dir = _hipconfig_query(hipconfig, "-l")
        sdk_compiler = root / "lib" / "llvm" / "bin" / "clang++"
        # The SDK's own compiler is the one that matches the deployed ROCm
        # runtime generation, so it wins over whatever hipconfig -l reports.
        hipcxx = str(sdk_compiler) if sdk_compiler.exists() else ""
        if not hipcxx and hipcxx_dir:
            reported = Path(hipcxx_dir) / "clang++"
            if reported.exists():
                hipcxx = str(reported)
        return RocmToolchain(
            root=root,
            hip_path=hip_path,
            hipcxx=hipcxx,
            hip_compiler=str(sdk_compiler),
            sdk_coherent=True,
            source=str(root),
        )

    # No SDK root: fall back to whichever hipconfig is on PATH.
    hipconfig = shutil.which("hipconfig") or "hipconfig"
    hipcxx_dir = _hipconfig_query(hipconfig, "-l")
    hip_path = _hipconfig_query(hipconfig, "-R")
    hipcxx = f"{hipcxx_dir}/clang" if hipcxx_dir else None
    return RocmToolchain(
        root=Path(hip_path) if hip_path else None,
        hip_path=hip_path or None,
        hipcxx=hipcxx,
        hip_compiler=hipcxx,
        sdk_coherent=False,
        source=f"PATH hipconfig ({hipconfig})",
    )


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
            except (OSError, RuntimeError) as exc:
                print_warning(f"Could not symlink {binary.name} → {link}: {exc}")
                logger.warning("Could not symlink %s: %s", binary, exc)


def _detect_distro() -> str:
    """Return a lowercase distro identifier string."""
    try:
        info = platform.freedesktop_os_release()
        return (info.get("ID", "") + " " + info.get("ID_LIKE", "")).lower().strip()
    except AttributeError:
        try:
            data: dict[str, str] = {}
            with open("/etc/os-release", encoding="utf-8") as fh:
                for line in fh:
                    if "=" in line:
                        k, _, v = line.partition("=")
                        data[k.strip()] = v.strip().strip('"\'')
            return (data.get("ID", "") + " " + data.get("ID_LIKE", "")).lower().strip()
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


def _has_vulkan_loader() -> bool:
    """Return True if the Vulkan loader/runtime is available to CMake."""
    for tool in ("pkgconf", "pkg-config"):
        if shutil.which(tool):
            try:
                if subprocess.run([tool, "--exists", "vulkan"],
                                  capture_output=True, timeout=5).returncode == 0:
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    if shutil.which("pacman"):
        try:
            if subprocess.run(["pacman", "-Qq", "vulkan-icd-loader"],
                              capture_output=True, timeout=5).returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    return any(path.exists() for path in _VULKAN_LOADER_LIBRARY_CANDIDATES)


def _has_vulkan_headers() -> bool:
    """Return True if Vulkan development headers are available.

    This must match the concrete include path that CMake's FindVulkan looks
    for. pkg-config `vulkan` is a loader signal on Arch/SteamOS, not a header
    signal, and it creates false positives.
    """
    return any(path.exists() for path in _VULKAN_HEADER_CANDIDATES)


def _has_spirv_headers() -> bool:
    """Return True if SPIRV-Headers development headers are available.

    Same strategy as _has_vulkan_headers: prefer package-manager queries over
    filesystem paths to avoid SteamOS overlay visibility issues.
    """
    for tool in ("pkgconf", "pkg-config"):
        if shutil.which(tool):
            try:
                if subprocess.run([tool, "--exists", "SPIRV-Headers"],
                                  capture_output=True, timeout=5).returncode == 0:
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    if shutil.which("pacman"):
        try:
            if subprocess.run(["pacman", "-Qq", "spirv-headers"],
                              capture_output=True, timeout=5).returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    return any(path.exists() for path in _SPIRV_HEADER_CANDIDATES)


def _has_c_runtime_headers() -> bool:
    """Return True when the active C compiler can resolve libc headers.

    SteamOS can report the compiler toolchain as installed while `/usr/include`
    is partially missing. Probe the actual compiler with `stdint.h` so preflight
    fails before Ninja reaches the first compile unit.
    """
    compiler = _find_first_available_command(("cc", "gcc", "clang"))
    if not compiler:
        return True

    try:
        return subprocess.run(
            [compiler, "-E", "-x", "c", "-"],
            input="#include <stdint.h>\n",
            text=True,
            capture_output=True,
            timeout=10,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _has_linux_api_headers() -> bool:
    """Return True when the active C compiler can resolve Linux UAPI headers.

    SteamOS package corruption can leave `/usr/include/linux` incomplete even
    after libc headers are repaired. Probe the kernel-facing headers directly so
    preflight catches missing linux-api-headers before Ninja starts compiling.
    """
    compiler = _find_first_available_command(("cc", "gcc", "clang"))
    if not compiler:
        return True

    try:
        return subprocess.run(
            [compiler, "-E", "-x", "c", "-"],
            input="#include <linux/errno.h>\n#include <linux/limits.h>\n#include <linux/types.h>\n",
            text=True,
            capture_output=True,
            timeout=10,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _detect_missing_linux_requirements(*, use_hip: bool) -> list[str]:
    missing: list[str] = []
    c_compiler = _find_first_available_command(("cc", "gcc", "clang"))
    cxx_compiler = _find_first_available_command(("c++", "g++", "clang++"))

    if not shutil.which("cmake"):
        missing.append("cmake")
    if not shutil.which("git"):
        missing.append("git")
    if not c_compiler:
        missing.append("C compiler")
    if not cxx_compiler:
        missing.append("C++ compiler")
    if c_compiler and not _has_c_runtime_headers():
        missing.append("C runtime headers")
    if c_compiler and not _has_linux_api_headers():
        missing.append("Linux API headers")
    if not shutil.which("ninja") and not shutil.which("make"):
        missing.append("build tool")

    if not use_hip:
        if not _has_vulkan_loader():
            missing.append("Vulkan loader")
        if not shutil.which("glslc"):
            missing.append("glslc")
        if not _has_vulkan_headers():
            missing.append("Vulkan headers")
        if not _has_spirv_headers():
            missing.append("SPIRV-Headers")

    return missing


def _build_linux_dependency_install_plan(distro: str, *, use_hip: bool) -> tuple[str, list[list[str]], bool] | None:
    if _is_debian_based(distro) and shutil.which("apt-get"):
        packages = ["build-essential", "linux-libc-dev", "cmake", "git", "ninja-build"]
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
        packages = ["base-devel", "linux-api-headers", "cmake", "git", "ninja"]
        if not use_hip:
            packages.extend(["shaderc", "spirv-headers", "vulkan-headers", "vulkan-icd-loader"])
        return (
            "pacman",
            [["pacman", "-S", "--needed", "--noconfirm", *_dedupe_preserve_order(packages)]],
            True,
        )

    dnf_binary = _find_first_available_command(("dnf5", "dnf", "yum"))
    if _is_fedora_based(distro) and dnf_binary:
        packages = ["cmake", "git", "gcc-c++", "kernel-headers", "make", "ninja-build"]
        if not use_hip:
            packages.extend(["vulkan-loader-devel", "shaderc", "spirv-headers-devel"])
        return (
            dnf_binary,
            [[dnf_binary, "install", "-y", *_dedupe_preserve_order(packages)]],
            True,
        )

    return None


def _build_arch_repair_package_list(missing_requirements: list[str]) -> list[str]:
    package_map = {
        "cmake": ["cmake"],
        "git": ["git"],
        "C compiler": ["base-devel"],
        "C++ compiler": ["base-devel"],
        "C runtime headers": ["glibc"],
        "Linux API headers": ["linux-api-headers"],
        "build tool": ["ninja"],
        "glslc": ["shaderc"],
        "Vulkan headers": ["vulkan-headers"],
        "Vulkan loader": ["vulkan-icd-loader"],
        "SPIRV-Headers": ["spirv-headers"],
    }

    repair_packages: list[str] = []
    for requirement in missing_requirements:
        repair_packages.extend(package_map.get(requirement, []))

    return _dedupe_preserve_order(repair_packages)


_PACMAN_KEYRING_DIR = Path("/etc/pacman.d/gnupg")
_PACMAN_DATABASE_DIR = Path("/var/lib/pacman")
_PACMAN_CACHE_DIR = Path("/var/cache/pacman/pkg")
_PACMAN_KEYRING_SEARCH_DIR = Path("/usr/share/pacman/keyrings")
_STEAMOS_KEYRING_CANDIDATES = ("archlinux", "holo", "jupiter", "steamos")


def _has_initialized_pacman_keyring() -> bool:
    # /etc/pacman.d/gnupg/ is root:root 700 — a non-root process cannot stat
    # files inside it even when the filesystem is unlocked.  Treat any access
    # denial as "not initialised" so the privileged pacman-key --init path runs.
    try:
        return (
            _PACMAN_KEYRING_DIR.exists()
            and (_PACMAN_KEYRING_DIR / "pubring.gpg").exists()
            and (_PACMAN_KEYRING_DIR / "trustdb.gpg").exists()
        )
    except PermissionError:
        return False


def _detect_available_pacman_keyrings() -> list[str]:
    keyrings: list[str] = []
    for name in _STEAMOS_KEYRING_CANDIDATES:
        if (_PACMAN_KEYRING_SEARCH_DIR / f"{name}.gpg").exists():
            keyrings.append(name)
    return keyrings or ["archlinux"]


def _verify_privileged_directory_is_writable(path: Path, description: str) -> None:
    probe = path / f".gillsystems-write-test-{os.getpid()}"
    try:
        _run_privileged(["mkdir", "-p", str(path)])
        _run_privileged(["touch", str(probe)])
        _run_privileged(["rm", "-f", str(probe)])
    except RuntimeError as exc:
        raise RuntimeError(
            f"SteamOS {description} is not writable after unlocking the filesystem: {path}"
        ) from exc


def _ensure_steamos_pacman_keyring() -> None:
    """Prepare SteamOS pacman state for package installation.

    SteamOS can fail package installs even after `steamos-readonly disable`
    if the pacman database/keyring tree is missing, partially initialized, or
    not writable. The Commander project hardens this by verifying write access
    explicitly before use; this updater follows the same pattern.
    """
    keyrings_to_populate = _detect_available_pacman_keyrings()

    try:
        print_step("Verifying SteamOS pacman filesystem state...")
        _verify_privileged_directory_is_writable(_PACMAN_DATABASE_DIR, "pacman database")
        _verify_privileged_directory_is_writable(_PACMAN_CACHE_DIR, "pacman cache")
        _verify_privileged_directory_is_writable(_PACMAN_KEYRING_DIR, "pacman keyring")
        _run_privileged(["chmod", "700", str(_PACMAN_KEYRING_DIR)])

        if not _has_initialized_pacman_keyring():
            print_step("Initialising pacman keyring (SteamOS first-run recovery)...")
            _run_privileged(["pacman-key", "--init"])

        for keyring in keyrings_to_populate:
            _run_privileged(["pacman-key", "--populate", keyring])
    except RuntimeError as exc:
        keyring_args = " ".join(keyrings_to_populate)
        raise RuntimeError(
            "SteamOS pacman recovery failed while preparing writable package-manager state. "
            f"Manual remediation: sudo steamos-readonly disable; sudo rm -rf {_PACMAN_KEYRING_DIR}; "
            f"sudo pacman-key --init; sudo pacman-key --populate {keyring_args}; "
            "sudo steamos-readonly enable"
        ) from exc

    print_info("SteamOS pacman state verified.")


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
        base_hint = "cmake, git, a C/C++ toolchain, Linux API headers, and either ninja or make"
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
    # Respect global unlock from the launcher (bootstrap-linux.sh sets STEAMOS_UNLOCKED=1
    # before Python starts). Re-locking mid-run would break the subsequent build/install.
    launcher_pre_unlocked = os.environ.get("STEAMOS_UNLOCKED") == "1"

    if dry_run:
        if steamos and not launcher_pre_unlocked:
            print_dry_run("Would unlock SteamOS read-only filesystem: steamos-readonly disable")
        if steamos:
            print_dry_run(
                "Would verify SteamOS pacman paths are writable: "
                f"{_PACMAN_DATABASE_DIR}, {_PACMAN_CACHE_DIR}, {_PACMAN_KEYRING_DIR}"
            )
            if not _has_initialized_pacman_keyring():
                print_dry_run("Would initialise pacman keyring: pacman-key --init")
            for keyring in _detect_available_pacman_keyrings():
                print_dry_run(f"Would populate pacman keyring: pacman-key --populate {keyring}")
        for command in commands:
            print_dry_run(f"Would install Linux build prerequisites: {' '.join(command)}")
        if steamos and not launcher_pre_unlocked:
            print_dry_run("Would re-lock SteamOS filesystem: steamos-readonly enable")
        return installs_ninja

    env = os.environ.copy()
    if package_manager == "apt-get":
        env["DEBIAN_FRONTEND"] = "noninteractive"

    if steamos and not launcher_pre_unlocked:
        print_step("SteamOS detected — temporarily disabling read-only filesystem...")
        try:
            _run_privileged(["steamos-readonly", "disable"])
        except RuntimeError as exc:
            raise RuntimeError(
                "Failed to disable SteamOS read-only filesystem. "
                "Manual unlock: sudo steamos-readonly disable"
            ) from exc

    try:
        if steamos:
            _ensure_steamos_pacman_keyring()
        for command in commands:
            _run_privileged(command, env=env)

        if package_manager == "pacman":
            remaining_requirements = _detect_missing_linux_requirements(use_hip=use_hip)
            repair_packages = _build_arch_repair_package_list(remaining_requirements)
            if repair_packages:
                print_warning(
                    "pacman reports required Arch packages as installed, but some files are still "
                    f"missing ({_format_missing_linux_requirements(remaining_requirements)}). "
                    f"Forcing targeted reinstall: {' '.join(repair_packages)}"
                )
                _run_privileged(["pacman", "-S", "--noconfirm", *repair_packages], env=env)
    finally:
        if steamos and not launcher_pre_unlocked:
            try:
                _run_privileged(["steamos-readonly", "enable"])
                print_info("SteamOS filesystem re-locked (read-only restored).")
            except RuntimeError as enable_exc:
                print_warning(
                    f"Failed to re-lock SteamOS filesystem: {enable_exc}. "
                    "Manually run: sudo steamos-readonly enable"
                )

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
