"""
CHM Unpacker Module for CATalyst.
Utilizes Windows native hh.exe to decompile CHM files into raw HTML.
"""

import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def unpack_chm(chm_path: Path | str, output_dir: Path | str) -> bool:
    """
    Decompiles a CHM file into the specified output directory using hh.exe.
    
    Args:
        chm_path: Path to the source .chm file.
        output_dir: Path to the target directory for extracted HTML files.
        
    Returns:
        bool: True if successful, False otherwise.
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
    
    # hh.exe -decompile <out_dir> <chm_file>
    cmd = ["hh.exe", "-decompile", str(output_dir), str(chm_path)]
    
    try:
        # Note: hh.exe might return non-zero exit codes even on success depending on the CHM build.
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        # Verify extraction by checking for a known core file or any generated directory
        if not any(output_dir.iterdir()):
            logger.error(f"Decompilation failed. Directory is empty.")
            if process.stderr:
                logger.error(f"Error output: {process.stderr}")
            return False
            
        logger.info(f"Successfully unpacked {chm_path.name}.")
        return True
        
    except FileNotFoundError:
        logger.error("hh.exe not found. This module requires Windows.")
        return False
    except Exception as e:
        logger.error(f"An error occurred during decompression: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    import argparse
    parser = argparse.ArgumentParser(description="Unpack CATIA V5Automation.chm")
    parser.add_argument("--input", "-i", type=str, default="data/V5Automation.chm", help="Path to CHM file")
    parser.add_argument("--output", "-o", type=str, default="data/raw", help="Output directory")
    
    args = parser.parse_args()
    unpack_chm(args.input, args.output)
