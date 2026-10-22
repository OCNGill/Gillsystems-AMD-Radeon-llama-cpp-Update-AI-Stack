"""
llama_builder.py (Windows) — Builds llama.cpp with AMD HIP backend on Windows.

Detects VS Build Tools / Developer Command Prompt, clones/pulls llama.cpp,
configures CMake with HIP backend, and builds with Ninja or MSBuild.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig
from src.gpu_detect import get_compute_tier

logger = logging.getLogger(__name__)

# VS Developer Command Prompt vcvarsall.bat search paths
_VCVARS_SEARCH_PATHS: list[str] = [
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
]

_HIP_RUNTIME_DLL_GLOBS: tuple[str, ...] = (
    "amdhip64*.dll",
    "libamdhip64*.dll",
    "amd_comgr*.dll",
    "hsa*.dll",
    "hip*.dll",
    "libhip*.dll",
    "roc*.dll",
    "libroc*.dll",
)

_MTP_HELP_MARKERS: tuple[str, ...] = (
    "--spec-type",
    "draft-mtp",
)


class LlamaBuilderWindows:
    """Clones, builds, and installs llama.cpp on Windows with AMD HIP."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig, gpu_targets: List[str]) -> None:
        self.cfg = cfg
        self.gpu_targets = gpu_targets
        self.source_dir = cfg.paths.resolve_llama_cpp_source()
        self.install_dir = cfg.paths.resolve_llama_cpp_install_windows()
        self.use_hip = False
        self.build_dir = self.source_dir / "build-vulkan-win"
        self._vcvars: Optional[Path] = None
        self._use_ninja: bool = False
        self._refresh_backend_selection()

    def _refresh_backend_selection(self) -> None:
        self.use_hip = bool(shutil.which("hipcc"))
        backend = "hip" if self.use_hip else "vulkan"
        self.build_dir = self.source_dir / f"build-{backend}-win"

    def build_and_install(self) -> None:
        """Full clone → configure → build → install cycle."""
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
        """Ensure cmake, git, and HIP SDK are available."""
        self._refresh_backend_selection()

        for tool in ("cmake", "git"):
            if not shutil.which(tool):
                raise RuntimeError(
                    f"Required tool '{tool}' not found. Install it before proceeding."
                )

        tier = get_compute_tier(self.gpu_targets)
        if not self.use_hip:
            if tier == 1:
                raise RuntimeError(
                    "hipcc not found. Tier 1 hardware REQUIRES the AMD HIP SDK. "
                    "Install it and ensure it is on PATH before proceeding."
                )
            else:
                print_warning("hipcc not found. Tier 2 hardware detected — falling back to Vulkan.")

        # Locate vcvarsall.bat
        for path_str in _VCVARS_SEARCH_PATHS:
            p = Path(path_str)
            if p.exists():
                self._vcvars = p
                break

        if not self._vcvars:
            if tier == 1:
                raise RuntimeError(
                    "Visual Studio Build Tools not found. "
                    "Tier 1 hardware requires MSVC for optimized ROCm/HIP compilation."
                )
            print_warning(
                "Visual Studio Build Tools not found. "
                "Attempting without vcvarsall.bat — build may fail."
            )

        # Prefer Ninja
        self._use_ninja = bool(shutil.which("ninja"))
        if not self._use_ninja:
            print_warning("Ninja not found — falling back to MSBuild (slower build).")
        else:
            print_info("Using Ninja build system.")

        if self.cfg.behavior.dry_run:
            print_dry_run("Pre-flight checks passed (dry-run).")

    # ------------------------------------------------------------------
    # Clone / Pull
    # ------------------------------------------------------------------

    def _clone_or_pull(self) -> None:
        # Windows uses the mainstream ggml-org fork (AMD has no native Windows ROCm build docs)
        repo_url = self.cfg.repo.llama_cpp_repo_windows

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
        self._refresh_backend_selection()

        # Find HIP_PATH from environment or default location
        hip_path = os.environ.get("HIP_PATH") or _find_hip_path()
        use_hip = self.use_hip

        cmake_args = [
            "cmake",
            "-S", str(self.source_dir),
            "-B", str(self.build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={self.install_dir}",
        ]

        if use_hip:
            enable_rocwmma = _hip_has_rocwmma(hip_path)
            cmake_args += [
                f"-DAMDGPU_TARGETS={targets_str}",
                "-DGGML_HIP=ON",
                "-DHIP_PLATFORM=amd",
                f"-DGGML_HIP_ROCWMMA_FATTN={'ON' if enable_rocwmma else 'OFF'}",
            ]
            if not enable_rocwmma:
                print_warning(
                    "HIP SDK does not include rocWMMA headers; disabling "
                    "GGML_HIP_ROCWMMA_FATTN on Windows."
                )
            if hip_path:
                # Add proper pathing for Findhip.cmake on Windows
                cmake_args.append(f"-DHIP_PATH={hip_path}")
                cmake_args.append(f"-DCMAKE_PREFIX_PATH={hip_path}")
                cmake_args.append(f"-Dhip_DIR={hip_path}/lib/cmake/hip")
                cmake_args.append(f"-Dhipblas_DIR={hip_path}/lib/cmake/hipblas")
                cmake_args.append(f"-Dhipblas-common_DIR={hip_path}/lib/cmake/hipblas-common")
                cmake_args.append(f"-Drocblas_DIR={hip_path}/lib/cmake/rocblas")
                cmake_args.append(f"-DAMDDeviceLibs_DIR={hip_path}/lib/cmake/AMDDeviceLibs")
        else:
            vulkan_sdk_path = _find_vulkan_sdk_path()
            vulkan_cmake_prefix = _find_vulkan_cmake_prefix(vulkan_sdk_path)
            if not vulkan_cmake_prefix:
                if vulkan_sdk_path:
                    raise RuntimeError(
                        "Tier 2 Vulkan fallback detected a Vulkan SDK at "
                        f"{vulkan_sdk_path}, but SPIRV-HeadersConfig.cmake was not found "
                        "under its CMake package directories. Repair or reinstall the "
                        "LunarG Vulkan SDK before proceeding."
                    )
                raise RuntimeError(
                    "Tier 2 Vulkan fallback requires the LunarG Vulkan SDK. Install it "
                    "or set VULKAN_SDK to the SDK root before proceeding."
                )

            cmake_args += [
                "-DGGML_VULKAN=ON",
                f"-DCMAKE_PREFIX_PATH={_merge_cmake_prefix_path(os.environ.get('CMAKE_PREFIX_PATH'), vulkan_cmake_prefix)}",
            ]
            print_info(
                "Enabling Vulkan backend (HIP fallback for mobile/edge targets). "
                f"Using SDK CMake prefix: {vulkan_cmake_prefix}"
            )

        if self._use_ninja:
            cmake_args += ["-GNinja"]
            if use_hip and hip_path:
                cmake_args += [
                    f"-DCMAKE_C_COMPILER={hip_path}/bin/clang.exe",
                    f"-DCMAKE_CXX_COMPILER={hip_path}/bin/clang++.exe",
                ]
        else:
            cmake_args += ["-G", "Visual Studio 17 2022", "-A", "x64"]

        if self.cfg.behavior.dry_run:
            if self.cfg.behavior.force and self.build_dir.exists():
                print_dry_run(f"Would delete stale cmake cache: {self.build_dir}")
            print_dry_run(f"Would configure: {' '.join(cmake_args)}")
            return

        # --force: nuke the cmake cache directory so stale HIP SDK links can't
        # persist and cause "unknown tensor" / wrong-version link failures.
        if self.cfg.behavior.force and self.build_dir.exists():
            print_step(f"--force: removing stale cmake cache at {self.build_dir}")
            shutil.rmtree(self.build_dir)
            print_success("Stale build directory removed.")

        print_step(f"Configuring CMake (targets: {targets_str})...")
        self.build_dir.mkdir(parents=True, exist_ok=True)

        env = _build_env(self._vcvars) if self._vcvars else None
        _run(cmake_args, env=env)
        print_success("CMake configuration complete.")

        # A HIP SDK upgrade swaps clang (e.g. 7.1 -> 7.2). CMake reacts by
        # deleting its own cache and re-running configure, and that re-configure
        # can silently drop -DGGML_HIP=ON. The result is a CPU-only build that
        # still "succeeds", leaving a stale ggml-hip.dll that no longer matches
        # the rebuilt ggml.dll -- the GPU backend then refuses to register.
        # Detect it and re-configure from a clean cache so the HIP flags stick.
        if use_hip and self._hip_backend_cache_state() == "off":
            print_warning(
                "CMake cache does not report GGML_HIP=ON after configure "
                "(the cache was invalidated by a compiler change). "
                "Re-configuring with a clean cache so the HIP backend is built."
            )
            cache_file = self.build_dir / "CMakeCache.txt"
            if cache_file.exists():
                cache_file.unlink()
            _run(cmake_args, env=env)
            if self._hip_backend_cache_state() == "off":
                raise RuntimeError(
                    "CMake still reports GGML_HIP=OFF after a clean re-configure. "
                    "Refusing to build a CPU-only llama.cpp."
                )
            print_success("Re-configured with a clean cache; HIP backend is enabled.")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        n_jobs = os.cpu_count() or 4

        env = _build_env(self._vcvars) if self._vcvars else os.environ.copy()
        if get_compute_tier(self.gpu_targets) == 2:
            print_info("Tier 2 Mobile/Edge architecture detected. Injecting LLAMA_HIP_UMA=1.")
            env["LLAMA_HIP_UMA"] = "1"

        if self._use_ninja:
            build_cmd = ["ninja", "-C", str(self.build_dir), f"-j{n_jobs}"]
        else:
            build_cmd = [
                "cmake", "--build", str(self.build_dir),
                "--config", "Release",
                f"--parallel", str(n_jobs),
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

    def _ensure_install_bin_is_real_dir(self) -> None:
        """Replace a junction/symlinked ``install_dir/bin`` with a real directory.

        If ``install_dir/bin`` is a junction into the build tree, every file
        operation on it (including the ``*.exe`` -> ``*.exe.old`` rename done
        to work around Windows file locks) lands in the build tree and destroys
        the freshly built binaries. The junction is removed with ``os.rmdir``
        (which deletes the link only, never the target contents) and replaced
        by a real directory so the install writes real files.
        """
        bin_dir = self.install_dir / "bin"
        if not _is_reparse_point(bin_dir):
            return

        target = ""
        try:
            target = f" -> {os.path.realpath(bin_dir)}"
        except OSError:
            pass

        print_warning(
            f"Install bin directory {bin_dir} is a link/junction{target}. "
            "Removing the link and installing into a real directory instead."
        )

        try:
            _remove_link(bin_dir)
        except OSError as exc:
            print_warning(
                f"Could not remove the link at {bin_dir} ({exc}). "
                "Continuing — the install may fail if the link points into the build tree."
            )
            return

        bin_dir.mkdir(parents=True, exist_ok=True)

    def _install(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would install binaries to {self.install_dir}")
            return

        # A junction/symlink at install_dir\bin can point straight into the build
        # tree. Renaming "*.exe" through such a link destroys the freshly built
        # binaries and makes `cmake --install` fail with "file INSTALL cannot find".
        # Replace the link with a real directory before touching any binary.
        self._ensure_install_bin_is_real_dir()

        # Repair any damage left behind by an earlier run that installed through
        # a junction (build outputs renamed to *.exe.old).
        _restore_stale_exe_old(self.build_dir)

        # Windows locks running .exe files. Rename any existing binaries out of
        # the way before cmake --install so we don't get "access denied" failures
        # when llama-server or llama-cli is still open in another terminal.
        renamed = _unlock_existing_binaries(self.install_dir, build_dir=self.build_dir)

        install_cmd = [
            "cmake", "--install", str(self.build_dir),
            "--config", "Release",
            "--prefix", str(self.install_dir),
        ]
        print_step(f"Installing binaries to {self.install_dir}...")
        self.install_dir.mkdir(parents=True, exist_ok=True)
        try:
            _run(install_cmd)
        except BaseException:
            # Restore the renamed binaries before propagating the failure so the
            # build tree / install tree is never left in a damaged state.
            _restore_renamed_binaries(renamed, installed=False)
            raise

        # Install succeeded: the freshly installed files occupy the target names,
        # so the renamed .exe.old copies are just litter and are removed.
        _restore_renamed_binaries(renamed, installed=True)
        print_success(f"Installed to {self.install_dir}")

        hip_path = os.environ.get("HIP_PATH") or _find_hip_path()
        if hip_path:
            copied = _bundle_hip_runtime_libraries(hip_path, self.install_dir / "bin")
            if copied:
                print_info(
                    f"Bundled {copied} HIP runtime DLL"
                    f"{'' if copied == 1 else 's'} into {self.install_dir / 'bin'}."
                )

            rocblas_library_dir = _bundle_rocblas_runtime_support(hip_path, self.install_dir / "bin")
            if rocblas_library_dir:
                print_info(f"Bundled rocBLAS support files into {rocblas_library_dir}.")
            else:
                print_warning(
                    "HIP SDK rocBLAS support files were not found. "
                    "HIP inference may fail if rocblas/library is unavailable at runtime."
                )

            for runtime_dir in _hip_runtime_dirs(hip_path):
                _append_to_user_path(str(runtime_dir))
                print_info(f"Added {runtime_dir} to user PATH.")

        # Add install bin dir to user PATH in registry
        bin_dir = str(self.install_dir / "bin")
        _append_to_user_path(bin_dir)
        print_info(f"Added {bin_dir} to user PATH.")

        mirrored_bin_dir = _mirror_install_bin_tree(
            self.install_dir / "bin",
            self.source_dir / "bin",
            build_dir=self.build_dir,
        )
        if mirrored_bin_dir:
            print_info(f"Mirrored installed binaries into {mirrored_bin_dir}.")

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def _hip_backend_cache_state(self) -> str:
        """Return "on", "off" or "unknown" for the CMake cache's HIP flag.

        "unknown" means CMake never wrote a cache we can read (or the entry is
        absent), so there is nothing to enforce.
        """
        cache_file = self.build_dir / "CMakeCache.txt"
        try:
            content = cache_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "unknown"
        match = re.search(r"^GGML_HIP:BOOL=(\w+)", content, re.MULTILINE)
        if not match:
            return "unknown"
        return "on" if match.group(1).upper() == "ON" else "off"

    def _verify_gpu_backend(self, runtime_env: dict) -> bool:
        """Prove the GPU backend actually runs kernels on the device.

        A CPU-only build passes every --version check, so the only honest test
        is to run a real kernel on the GPU and look for the device by name.
        """
        if not self.use_hip:
            return True

        ops = self.install_dir / "bin" / "test-backend-ops.exe"
        if ops.exists():
            try:
                result = subprocess.run(
                    [str(ops), "-b", "ROCm0", "-o", "ADD"],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    env=runtime_env,
                )
            except Exception as exc:
                print_warning(f"ROCm backend probe could not run: {exc}")
                return False
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0 and "ROCm" in output and not re.search(r"\bFAIL\b", output):
                print_success("ROCm0 backend verified: ADD kernel executed on the GPU.")
                return True
            print_warning(
                "ROCm0 backend probe did not pass -- the GPU backend is not usable."
            )
            return False

        cli = self.install_dir / "bin" / "llama-cli.exe"
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
                return False
            output = (result.stdout or "") + (result.stderr or "")
            if re.search(r"(AMD|Radeon|ROCm)", output, re.IGNORECASE):
                print_success("GPU device enumerated via llama-cli --list-devices.")
                return True
            print_warning("llama-cli --list-devices showed no AMD/ROCm device.")
            return False

        print_warning("No probe binary available to verify the GPU backend.")
        return False

    def _validate(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: llama-cli.exe --version")
            return

        hip_path = os.environ.get("HIP_PATH") or _find_hip_path()
        runtime_env = _prepend_to_path_env(
            os.environ.copy(),
            [str(self.install_dir / "bin"), *[str(path) for path in _hip_runtime_dirs(hip_path)]],
        )
        rocblas_tensile_libpath = _resolve_rocblas_tensile_libpath(self.install_dir / "bin", hip_path)
        if rocblas_tensile_libpath:
            runtime_env["ROCBLAS_TENSILE_LIBPATH"] = rocblas_tensile_libpath

        validated_binary: Optional[Path] = None
        for binary in ("llama-cli.exe", "llama-server.exe", "main.exe"):
            bin_path = self.install_dir / "bin" / binary
            if bin_path.exists():
                try:
                    result = subprocess.run(
                        [str(bin_path), "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        env=runtime_env,
                    )
                    output_lines = (result.stdout + result.stderr).strip().splitlines()
                    first_line = output_lines[0] if output_lines else "(no version output)"
                    if result.returncode == 0:
                        print_success(f"{binary}: {first_line[:80]}")
                        validated_binary = bin_path
                        break
                    print_warning(
                        f"{binary} exited with code {result.returncode}: {first_line[:120]}"
                    )
                except Exception as exc:
                    print_warning(f"Could not run {binary}: {exc}")

        if not validated_binary:
            raise RuntimeError(
                "No llama.cpp binary in the install tree could be executed "
                "(--version failed). The installation is not usable."
            )

        if not self._verify_gpu_backend(runtime_env):
            raise RuntimeError(
                "llama.cpp was installed but no ROCm device could be verified. "
                "The build is CPU-only or the GPU backend failed to register. "
                "Refusing to report a successful update."
            )

        mtp_check_binary = next(
            (
                self.install_dir / "bin" / name
                for name in ("llama-server.exe", "llama-cli.exe")
                if (self.install_dir / "bin" / name).exists()
            ),
            validated_binary,
        )

        try:
            result = subprocess.run(
                [str(mtp_check_binary), "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                env=runtime_env,
            )
            help_text = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0 and all(marker in help_text for marker in _MTP_HELP_MARKERS):
                print_success(
                    f"{mtp_check_binary.name}: speculative MTP CLI options detected "
                    "(binary capability only; model GGUF must include MTP layers)."
                )
            else:
                print_warning(
                    f"{mtp_check_binary.name} did not advertise draft-mtp support in --help output."
                )
        except Exception as exc:
            print_warning(f"Could not inspect {mtp_check_binary.name} --help: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_reparse_point(path: Path) -> bool:
    """Return True when *path* is a symlink, junction, or other reparse point.

    On Windows a directory junction is not reported by ``os.path.islink`` (that
    only covers symlinks), so the reparse-point file attribute is checked as
    well. The attribute constant is looked up defensively so the helper also
    works on non-Windows platforms.
    """
    try:
        if os.path.islink(path):
            return True
        status = os.lstat(path)
    except OSError:
        return False

    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _remove_link(path: Path) -> None:
    """Delete a symlink/junction without touching the contents of its target.

    ``os.rmdir`` on a junction removes the link only; ``os.unlink`` is used for
    symlinks (on POSIX ``rmdir`` on a symlink fails with ENOTDIR). On Windows a
    directory symlink cannot be unlinked, so the rmdir fallback is used there.
    """
    if os.path.islink(path):
        try:
            os.unlink(path)
            return
        except OSError:
            pass

    try:
        os.rmdir(path)
    except OSError:
        os.unlink(path)


def _is_within(child: str, parent: str) -> bool:
    """Return True when *child* resolves to a location inside *parent*."""
    try:
        child_norm = os.path.normcase(os.path.abspath(child))
        parent_norm = os.path.normcase(os.path.abspath(parent))
        return os.path.normcase(os.path.commonpath([child_norm, parent_norm])) == parent_norm
    except ValueError:
        return False


def _unlock_existing_binaries(
    install_dir: Path,
    build_dir: Optional[Path] = None,
) -> List[tuple]:
    """Rename existing llama binaries before install to avoid Windows file-locking errors.

    If llama-cli.exe or llama-server.exe is open in another terminal, cmake --install
    will fail with "access denied". Renaming to .exe.old lets the install proceed;
    the old file is cleaned up on the next successful install.

    Candidates that resolve inside *build_dir* are never renamed: renaming a
    build output destroys the artifact the install step is about to copy. This
    is the defence-in-depth for an install ``bin`` directory that is a junction
    pointing into the build tree.

    Returns the list of ``(original, renamed)`` pairs so the caller can restore
    them after the install attempt.
    """
    bin_dir = install_dir / "bin"
    if not bin_dir.exists():
        return []

    build_root: Optional[str] = None
    if build_dir is not None:
        try:
            build_root = os.path.realpath(build_dir)
        except OSError:
            build_root = None

    renamed: List[tuple] = []
    for exe in sorted(bin_dir.glob("*.exe")):
        if build_root is not None:
            try:
                resolved = os.path.realpath(exe)
            except OSError:
                resolved = str(exe)
            if _is_within(resolved, build_root):
                print_warning(
                    f"Skipping {exe.name} — it resolves inside the build directory "
                    f"({build_root}) and must not be renamed."
                )
                continue

        stale = exe.with_suffix(".exe.old")
        try:
            stale.unlink(missing_ok=True)
            exe.rename(stale)
        except OSError as exc:
            print_warning(
                f"Could not rename {exe.name} ({exc}). "
                "If it is currently running, stop it before installing or the install may fail."
            )
            continue
        renamed.append((exe, stale))

    return renamed


def _restore_renamed_binaries(renamed: List[tuple], installed: bool) -> None:
    """Restore binaries renamed by :func:`_unlock_existing_binaries`.

    A renamed file is put back under its original name so no binary is lost and
    no ``.exe.old`` litter is left behind:

    * when the original name is free the backup is simply renamed back;
    * when the original name is occupied by a file the install step just wrote,
      that file is dropped and the backup is renamed back (the install failed),
      or the backup is deleted (the install succeeded and the fresh file wins).
    """
    for original, stale in renamed:
        if not stale.exists():
            continue

        if original.exists():
            if installed:
                # The install step produced a fresh file under the target name.
                try:
                    stale.unlink(missing_ok=True)
                except OSError as exc:
                    print_warning(f"Could not remove stale {stale.name}: {exc}")
                continue

            # The install failed: drop the partial file and put the original back.
            try:
                original.unlink(missing_ok=True)
                stale.rename(original)
            except OSError as exc:
                print_warning(
                    f"Could not restore {original.name} from {stale.name}: {exc}"
                )
            continue

        try:
            stale.rename(original)
        except OSError as exc:
            print_warning(f"Could not restore {original.name} from {stale.name}: {exc}")


def _restore_stale_exe_old(build_dir: Path) -> List[Path]:
    """Clean up leftover ``*.exe.old`` files in a build tree.

    A previous run that installed through a junction renamed the freshly built
    binaries inside the build tree to ``*.exe.old``. When the original ``.exe``
    is missing the backup is restored under its original name; when the original
    is already present the backup is pure litter and is removed.
    """
    bin_dir = build_dir / "bin"
    if not bin_dir.is_dir():
        return []

    restored: List[Path] = []
    for stale in sorted(bin_dir.glob("*.exe.old")):
        original = stale.with_suffix("")
        if original.exists():
            try:
                stale.unlink(missing_ok=True)
            except OSError as exc:
                print_warning(f"Could not remove stale {stale.name} in {bin_dir}: {exc}")
            continue
        try:
            stale.rename(original)
        except OSError as exc:
            print_warning(f"Could not restore {stale.name} in {bin_dir}: {exc}")
            continue
        restored.append(original)

    return restored


def _find_hip_path() -> Optional[str]:
    """Try to locate the HIP SDK installation directory.

    Searches newest-first so that the latest installed version wins.
    Covers ROCm 7.x (current as of HIP SDK 7.2.2) down to 6.x legacy.
    """
    candidates = [
        # ROCm 7.x — current requirement per AMD / Gemma 4 compatibility
        r"C:\Program Files\AMD\ROCm\7.3",
        r"C:\Program Files\AMD\ROCm\7.2",
        r"C:\Program Files\AMD\ROCm\7.1",
        r"C:\Program Files\AMD\ROCm\7.0",
        # ROCm 6.x — legacy fallback
        r"C:\Program Files\AMD\ROCm\6.3",
        r"C:\Program Files\AMD\ROCm\6.2",
        r"C:\Program Files\AMD\ROCm\6.1",
        # Generic / symlinked install
        r"C:\Program Files\AMD\ROCm",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _find_vulkan_sdk_path() -> Optional[str]:
    """Try to locate the installed Vulkan SDK root directory on Windows."""
    for env_var in ("VULKAN_SDK", "VK_SDK_PATH"):
        candidate = os.environ.get(env_var)
        if candidate and Path(candidate).exists():
            return candidate

    for sdk_root in (Path(r"C:\VulkanSDK"), Path(r"C:\Program Files\VulkanSDK")):
        if not sdk_root.exists():
            continue

        version_dirs = [child for child in sdk_root.iterdir() if child.is_dir()]
        for version_dir in sorted(version_dirs, key=_version_sort_key, reverse=True):
            return str(version_dir)

    return None


def _find_vulkan_cmake_prefix(vulkan_sdk_path: Optional[str]) -> Optional[str]:
    """Return the Vulkan SDK CMake prefix that exposes SPIRV-Headers."""
    if not vulkan_sdk_path:
        return None

    sdk_root = Path(vulkan_sdk_path)
    candidates = [
        sdk_root,
        sdk_root / "Lib" / "cmake",
        sdk_root / "lib" / "cmake",
        sdk_root / "cmake",
    ]
    for candidate in candidates:
        if (candidate / "SPIRV-Headers" / "SPIRV-HeadersConfig.cmake").exists():
            return str(candidate)
        if (candidate / "SPIRV-HeadersConfig.cmake").exists():
            return str(candidate)

    return None


def _merge_cmake_prefix_path(*prefix_groups: Optional[str]) -> str:
    """Combine CMake prefix path fragments while preserving their order."""
    prefixes: list[str] = []
    seen: set[str] = set()

    for prefix_group in prefix_groups:
        if not prefix_group:
            continue
        for prefix in str(prefix_group).split(";"):
            normalized = prefix.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            prefixes.append(normalized)

    return ";".join(prefixes)


def _version_sort_key(path: Path) -> tuple[int, ...]:
    """Sort Vulkan SDK version directories newest-first."""
    version_parts: list[int] = []
    for token in path.name.replace("-", ".").split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            version_parts.append(int(digits))
    return tuple(version_parts or [0])


def _hip_has_rocwmma(hip_path: Optional[str]) -> bool:
    """Return True when the installed HIP SDK exposes the rocWMMA header set."""
    if not hip_path:
        return False
    return Path(hip_path, "include", "rocwmma", "rocwmma-version.hpp").exists()


def _hip_runtime_dirs(hip_path: Optional[str]) -> list[Path]:
    """Return existing directories that can contain Windows HIP runtime DLLs."""
    if not hip_path:
        return []

    hip_root = Path(hip_path)
    candidates = [hip_root / "bin", hip_root / "lib", hip_root / "lib64"]
    return [candidate for candidate in candidates if candidate.exists()]


def _bundle_hip_runtime_libraries(hip_path: Optional[str], install_bin: Path) -> int:
    """Copy HIP runtime DLLs next to llama.cpp binaries for reliable Windows launches."""
    runtime_dirs = _hip_runtime_dirs(hip_path)
    if not runtime_dirs:
        return 0

    install_bin.mkdir(parents=True, exist_ok=True)

    copied = 0
    seen: set[str] = set()
    for runtime_dir in runtime_dirs:
        for pattern in _HIP_RUNTIME_DLL_GLOBS:
            for dll_path in runtime_dir.glob(pattern):
                dll_key = dll_path.name.lower()
                if dll_key in seen:
                    continue
                shutil.copy2(dll_path, install_bin / dll_path.name)
                seen.add(dll_key)
                copied += 1

    return copied


def _hip_rocblas_runtime_dir(hip_path: Optional[str]) -> Optional[Path]:
    """Return the HIP SDK rocBLAS runtime directory when it ships Tensile data files."""
    if not hip_path:
        return None

    hip_root = Path(hip_path)
    candidates = [
        hip_root / "bin" / "rocblas",
        hip_root / "rocblas",
    ]
    for candidate in candidates:
        if (candidate / "library").exists():
            return candidate
    return None


def _bundle_rocblas_runtime_support(hip_path: Optional[str], install_bin: Path) -> Optional[Path]:
    """Copy rocBLAS support files so bundled rocblas.dll can locate Tensile data on Windows."""
    rocblas_dir = _hip_rocblas_runtime_dir(hip_path)
    if not rocblas_dir:
        return None

    destination = install_bin / "rocblas"
    shutil.copytree(rocblas_dir, destination, dirs_exist_ok=True)
    return destination / "library"


def _resolve_rocblas_tensile_libpath(install_bin: Path, hip_path: Optional[str]) -> Optional[str]:
    """Return the best rocBLAS Tensile library path for runtime launches."""
    bundled = install_bin / "rocblas" / "library"
    if bundled.exists():
        return str(bundled)

    rocblas_dir = _hip_rocblas_runtime_dir(hip_path)
    if rocblas_dir:
        return str(rocblas_dir / "library")

    return None


def _mirror_install_bin_tree(
    install_bin: Path,
    source_bin: Path,
    build_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Copy the canonical install bin tree into the source-root bin directory.

    A junction or symlink at *source_bin* is never followed: ``shutil.rmtree``
    on a junction deletes the contents of its *target* (which can be the build
    tree), and copying through it would move build outputs into the source tree.
    Such a link is replaced by a real directory instead.
    """
    if not install_bin.exists():
        return None

    if install_bin.resolve(strict=False) == source_bin.resolve(strict=False):
        return None

    if _is_reparse_point(install_bin):
        print_warning(
            f"Install bin directory {install_bin} is still a link/junction — "
            "skipping the mirror so build outputs are not copied into the source tree."
        )
        return None

    if _is_reparse_point(source_bin):
        print_warning(
            f"Source bin directory {source_bin} is a link/junction — "
            "replacing it with a real directory before mirroring."
        )
        try:
            _remove_link(source_bin)
        except OSError as exc:
            print_warning(f"Could not remove the link at {source_bin} ({exc}).")
            return None
    elif source_bin.is_file():
        source_bin.unlink()
    elif source_bin.exists():
        shutil.rmtree(source_bin)

    if build_dir is not None:
        try:
            build_root = os.path.realpath(build_dir)
            if _is_within(os.path.realpath(source_bin), build_root):
                print_warning(
                    f"Refusing to mirror into {source_bin} — it resolves inside the "
                    f"build directory ({build_root})."
                )
                return None
        except OSError:
            pass

    shutil.copytree(install_bin, source_bin)
    return source_bin


def _prepend_to_path_env(base_env: dict, extra_dirs: list[str]) -> dict:
    """Return an env copy with extra directories prepended to PATH once each."""
    env = base_env.copy()
    unique_dirs: list[str] = []
    seen: set[str] = set()

    for entry in extra_dirs:
        normalized = entry.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_dirs.append(normalized)

    if not unique_dirs:
        return env

    current_path = env.get("PATH", "")
    env["PATH"] = ";".join(unique_dirs + ([current_path] if current_path else []))
    return env


def _build_env(vcvars: Path) -> dict:
    """
    Return an environment dict that includes VS build tool variables.
    Starts from the current process environment (so TMP, TEMP, SystemRoot,
    USERPROFILE, etc. are always present) then overlays vcvarsall.bat output
    so MSVC-specific vars (LIB, INCLUDE, PATH extensions) are added on top.
    """
    script = f'call "{vcvars}" amd64 && set'
    result = subprocess.run(
        ["cmd", "/c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        logger.warning("vcvarsall.bat returned non-zero (%d); MSVC env may be incomplete.", result.returncode)
    # Base on current process env so TMP, TEMP, SystemRoot, etc. are always
    # present — vcvarsall.bat only adds/modifies MSVC-specific variables.
    env = os.environ.copy()
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _run(cmd: list[str], timeout: int = 3600, env: Optional[dict] = None) -> None:
    """Run a command; raises on failure."""
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=timeout, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def _append_to_user_path(new_dir: str) -> None:
    """Add a directory to the current process PATH and the current user's PATH."""
    current_process_paths = [path.strip() for path in os.environ.get("PATH", "").split(";") if path.strip()]
    if new_dir.lower() not in {path.lower() for path in current_process_paths}:
        current_process_env = _prepend_to_path_env(dict(os.environ), [new_dir])
        os.environ["PATH"] = current_process_env.get("PATH", os.environ.get("PATH", ""))

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
        )
        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""
        paths = [p.strip() for p in current_path.split(";") if p.strip()]
        existing_paths = {path.lower() for path in paths}
        if new_dir.lower() not in existing_paths:
            paths.append(new_dir)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(paths))
        winreg.CloseKey(key)
    except Exception as exc:
        logger.warning("Could not update user PATH: %s", exc)
