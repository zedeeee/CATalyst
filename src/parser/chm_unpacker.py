"""
CHM Unpacker Module for CATalyst.
Supports 7-Zip (fast, space-safe, cross-platform) with automatic fallback to Windows native hh.exe
using an isolated spaceless staging directory to avoid hh.exe's space-in-path silent failure bug.
"""

import ctypes
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _has_extracted_html(output_dir: Path) -> bool:
    """Verify real HTML files were extracted (never mistake .gitkeep for unpacked output)."""
    if not output_dir.is_dir():
        return False
    for pattern in ("*.htm", "*.html"):
        if next(output_dir.rglob(pattern), None) is not None:
            return True
    return False


def _find_7z() -> Optional[str]:
    """
    Locate 7z / 7za / 7zz executable from:
    1. CATALYST_7Z_PATH env override
    2. System PATH (7z, 7za, 7zz)
    3. Standard Windows install locations (7-Zip, Scoop, Chocolatey)
    """
    env_7z = os.environ.get("CATALYST_7Z_PATH", "").strip().strip('"').strip("'")
    if env_7z and Path(env_7z).is_file():
        return str(Path(env_7z).resolve())

    for name in ("7z", "7za", "7zz"):
        found = shutil.which(name)
        if found:
            return found

    if os.name == "nt":
        home = Path.home()
        for candidate in (
            Path(r"C:\Program Files\7-Zip\7z.exe"),
            Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
            home / "scoop" / "shims" / "7z.exe",
            Path(r"C:\ProgramData\chocolatey\bin\7z.exe"),
        ):
            if candidate.is_file():
                return str(candidate)
    return None


def _find_hh() -> Optional[str]:
    """Locate Windows native hh.exe."""
    if os.name != "nt":
        return None
    hh_bin = shutil.which("hh.exe")
    if hh_bin:
        return hh_bin
    win_hh = Path(os.environ.get("WINDIR", r"C:\Windows")) / "hh.exe"
    if win_hh.is_file():
        return str(win_hh)
    return None


def detect_unpacker_backend() -> Tuple[str, Optional[str]]:
    """Return the active CHM unpacker backend: ('7z', path), ('hh', path), or ('none', None)."""
    seven_zip = _find_7z()
    if seven_zip:
        return ("7z", seven_zip)
    hh_bin = _find_hh()
    if hh_bin:
        return ("hh", hh_bin)
    return ("none", None)


def _to_windows_short_path(path: Path) -> str:
    """Convert a path containing spaces to its 8.3 short path on Windows when supported."""
    if os.name != "nt":
        return str(path)
    try:
        buf = ctypes.create_unicode_buffer(1024)
        res = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
        if res and res < len(buf) and buf.value:
            return buf.value
    except Exception:
        pass
    return str(path)


def _pick_spaceless_temp_base(output_dir: Path) -> Optional[str]:
    """Choose a writable temp base directory without spaces when possible."""
    default_tmp = tempfile.gettempdir()
    if " " not in default_tmp:
        return None

    candidates: list[Path] = [output_dir.parent]
    if os.name == "nt":
        drive_root = Path(output_dir.drive + "\\") if output_dir.drive else Path("C:\\")
        candidates.extend([drive_root / "Temp", Path("C:/Temp"), Path("C:/Windows/Temp")])

    seen: set[str] = set()
    for cand in candidates:
        cand_str = str(cand)
        if cand_str in seen or " " in cand_str:
            continue
        seen.add(cand_str)
        if cand.is_dir() and os.access(cand, os.W_OK):
            return cand_str
    return None


def _unpack_with_7z(chm_path: Path, output_dir: Path, seven_zip: str) -> bool:
    """Extract CHM archive via 7-Zip (argv list, space-in-path safe for both source and target)."""
    cmd = [seven_zip, "x", str(chm_path), f"-o{output_dir}", "-y"]
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if _has_extracted_html(output_dir):
            return True
        if process.stderr:
            logger.debug("7z stderr: %s", process.stderr.strip())
        return False
    except OSError as e:
        logger.debug("7z invocation failed: %s", e)
        return False


def _unpack_with_hh(chm_path: Path, output_dir: Path) -> bool:
    """
    Extract CHM via Windows native hh.exe using a spaceless temporary directory.
    hh.exe -decompile frequently fails silently when source or target paths contain spaces
    (e.g. 'C:\\Program Files\\Dassault Systemes\\...').
    """
    hh_bin = _find_hh()
    if not hh_bin:
        return False

    temp_base = _pick_spaceless_temp_base(output_dir)

    with tempfile.TemporaryDirectory(prefix="catalyst_chm_", dir=temp_base) as tmp:
        tmp_dir = Path(tmp)
        staged_chm = tmp_dir / "source.chm"
        staged_out = tmp_dir / "out"
        staged_out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chm_path, staged_chm)

        run_cwd = str(tmp_dir)
        if " " in run_cwd:
            short_cwd = _to_windows_short_path(tmp_dir)
            if " " in short_cwd:
                logger.error(
                    "hh.exe requires a spaceless staging directory, but both TEMP (%s) and its "
                    "8.3 short path still contain spaces. Please install 7-Zip (`winget install 7zip.7zip`).",
                    tmp_dir,
                )
                return False
            run_cwd = short_cwd

        try:
            # Note: hh.exe might return non-zero exit codes even on success depending on the CHM build.
            process = subprocess.run(
                [hh_bin, "-decompile", "out", "source.chm"],
                cwd=run_cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            if not _has_extracted_html(staged_out):
                if process.stderr:
                    logger.debug("hh.exe stderr: %s", process.stderr.strip())
                return False

            for item in staged_out.iterdir():
                target = output_dir / item.name
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                shutil.move(str(item), str(target))
            return _has_extracted_html(output_dir)
        except OSError as e:
            logger.debug("hh.exe invocation failed: %s", e)
            return False


def ensure_unpacker_choice(
    *,
    interactive: bool,
    allow_hh_fallback: bool = False,
) -> Tuple[bool, bool]:
    """
    Ensure a CHM unpacker is ready without silently switching away from 7-Zip.
    Returns (is_ready, allow_hh_fallback).
    """
    if _find_7z():
        return (True, allow_hh_fallback)

    if allow_hh_fallback and os.name == "nt" and _find_hh():
        return (True, True)

    if not interactive:
        if os.name == "nt":
            print("\n[ERROR] 未检测到 7-Zip（推荐用于稳定解压含空格路径的 CHM 文件）。")
            print("        请选择以下任一方式后重试：")
            print("        1) 安装 7-Zip（推荐）：winget install 7zip.7zip")
            print("        2) 指定已有 7z 路径：--7z \"<path-to-7z.exe>\"")
            print("        3) 显式使用 Windows 原生 hh.exe：追加参数 --use-hh")
        else:
            print("\n[ERROR] 未检测到 7-Zip (7z/7za/7zz)，当前系统无法直接解包 .chm 文件。")
            print("        请选择以下任一方式后重试：")
            print("        1) 安装 7-Zip：macOS `brew install p7zip` / Ubuntu `sudo apt install p7zip-full`")
            print("        2) 指定已有 7z 路径：--7z \"<path-to-7z>\"")
            print("        3) 直接复用已在 Windows 上构建好的 dist/catalyst.db")
        return (False, False)

    # Interactive terminal: let the user explicitly choose
    has_hh = os.name == "nt" and bool(_find_hh())
    print("\n[ACTION REQUIRED] 未检测到 7-Zip（推荐，解压最快且完全免疫含空格路径）。")
    if os.name == "nt":
        print("  [1] 中断安装，先去安装 7-Zip（推荐：winget install 7zip.7zip） [默认]")
        print("  [2] 手动指定已安装的 7z.exe 路径")
        if has_hh:
            print("  [3] 直接使用 Windows 原生 hh.exe 继续解压")
    else:
        print("  [1] 中断安装，先去安装 7-Zip（macOS: brew install p7zip / Ubuntu: sudo apt install p7zip-full） [默认]")
        print("  [2] 手动指定已安装的 7z / 7za 路径")

    while True:
        prompt_opts = "[1/2/3，默认 1]" if has_hh else "[1/2，默认 1]"
        try:
            choice = input(f"请选择处理方式 {prompt_opts}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return (False, False)

        if choice in ("", "1"):
            print("  [EXIT] 已中断安装。安装好 7-Zip 后重新运行安装命令即可。")
            return (False, False)
        if choice == "2":
            from src.engine.local_config import parse_user_path

            try:
                raw = input("请输入 7z 可执行文件完整路径: ").strip()
            except (EOFError, KeyboardInterrupt):
                return (False, False)
            p = parse_user_path(raw)
            if p and p.is_file():
                os.environ["CATALYST_7Z_PATH"] = str(p.resolve())
                print(f"  [OK] 已采用 7-Zip: {p.resolve()}")
                return (True, False)
            print(f"  [INVALID] 未找到文件: {raw}，请重新选择。")
            continue
        if choice == "3" and has_hh:
            print("  [OK] 已选择使用 Windows 原生 hh.exe（无空格临时目录模式）继续。")
            return (True, True)
        print("  [INVALID] 无效选项，请输入对应数字。")


def unpack_chm(
    chm_path: Path | str,
    output_dir: Path | str,
    *,
    allow_hh_fallback: bool = False,
) -> bool:
    """
    Decompiles a CHM file into the specified output directory.
    Uses 7-Zip by default; only invokes Windows native hh.exe when allow_hh_fallback=True.

    Args:
        chm_path: Path to the source .chm file.
        output_dir: Path to the target directory for extracted HTML files.
        allow_hh_fallback: Explicitly authorize Windows hh.exe when 7-Zip is unavailable.

    Returns:
        bool: True if HTML files were successfully extracted, False otherwise.
    """
    chm_path = Path(chm_path).resolve()
    output_dir = Path(output_dir).resolve()

    if not chm_path.exists():
        logger.error(f"CHM file not found: {chm_path}")
        return False

    if not chm_path.is_file() or chm_path.suffix.lower() != '.chm':
        logger.error(f"Invalid CHM file: {chm_path}")
        return False

    # Prevent accidental deletion if the output dir is the root or critical path
    if output_dir.exists() and len(list(output_dir.iterdir())) > 0:
        # Check for a specific gitkeep to know it's our managed dir
        if not (output_dir / ".gitkeep").exists():
            logger.warning(f"Output directory {output_dir} is not empty and lacks .gitkeep. Proceeding with caution.")

        logger.info(f"Clearing existing output directory contents: {output_dir}")
        for item in output_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                logger.error(f"Failed to delete {item}: {e}")
                return False

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Unpacking {chm_path.name} to {output_dir}...")
    tried: list[str] = []

    seven_zip = _find_7z()
    if seven_zip:
        tried.append(f"7z ({seven_zip})")
        if _unpack_with_7z(chm_path, output_dir, seven_zip):
            logger.info(f"Successfully unpacked {chm_path.name} via 7-Zip.")
            return True
        if not allow_hh_fallback:
            logger.error("7-Zip extraction produced no HTML files. Pass --use-hh on Windows to try hh.exe.")
            return False
        logger.warning("7-Zip extraction produced no HTML files; trying explicitly enabled hh.exe...")

    if allow_hh_fallback and os.name == "nt":
        tried.append("hh.exe (spaceless staging)")
        if _unpack_with_hh(chm_path, output_dir):
            logger.info(f"Successfully unpacked {chm_path.name} via hh.exe.")
            return True

    hint = (
        "Install 7-Zip (`winget install 7zip.7zip`), set CATALYST_7Z_PATH, or pass `--use-hh`."
        if os.name == "nt"
        else "Install 7-Zip (`brew install p7zip` on macOS or `sudo apt install p7zip-full` on Debian/Ubuntu), "
        "or copy a pre-built dist/catalyst.db from Windows."
    )
    logger.error(
        "Decompilation failed: no HTML files extracted to %s (tried: %s). %s",
        output_dir,
        ", ".join(tried) or "none",
        hint,
    )
    return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    import argparse
    parser = argparse.ArgumentParser(description="Unpack CATIA V5Automation.chm")
    parser.add_argument("--input", "-i", type=str, default="data/V5Automation.chm", help="Path to CHM file")
    parser.add_argument("--output", "-o", type=str, default="data/raw", help="Output directory")
    
    args = parser.parse_args()
    unpack_chm(args.input, args.output)
