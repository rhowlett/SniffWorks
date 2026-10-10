"""
dwf_loader.py
Loads the Digilent WaveForms DWF shared library on macOS and Linux.
Also loads dwfconstants from the WaveForms SDK installation.
"""

import sys
import os
import ctypes
import importlib.util
from pathlib import Path


class DWFLoadError(RuntimeError):
    pass


def _find_dwfconstants():
    """Search known SDK paths for dwfconstants.py and return the module."""
    search_paths = []

    if sys.platform.startswith("darwin"):
        search_paths = [
            "/Applications/WaveForms.app/Contents/Resources/SDK/samples/py",
            os.path.expanduser("~/Applications/WaveForms.app/Contents/Resources/SDK/samples/py"),
        ]
    else:
        # Linux
        search_paths = [
            "/usr/share/digilent/waveforms/samples/py",
            "/usr/local/share/digilent/waveforms/samples/py",
        ]

    # Also check if user has placed dwfconstants.py next to this file
    search_paths.insert(0, str(Path(__file__).parent.parent))
    search_paths.insert(0, str(Path(__file__).parent))

    for p in search_paths:
        candidate = os.path.join(p, "dwfconstants.py")
        if os.path.isfile(candidate):
            spec = importlib.util.spec_from_file_location("dwfconstants", candidate)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, candidate

    return None, None


def load_dwf():
    """
    Load the DWF library and dwfconstants.
    Returns (dwf_lib, constants_module, constants_path).
    Raises DWFLoadError on failure.
    """
    # --- load the shared library ---
    if sys.platform.startswith("darwin"):
        lib_path = "/Library/Frameworks/dwf.framework/dwf"
        try:
            dwf = ctypes.cdll.LoadLibrary(lib_path)
        except OSError as e:
            raise DWFLoadError(
                f"Could not load DWF library at '{lib_path}'.\n"
                "Please install WaveForms from https://digilent.com/shop/software/digilent-waveforms/\n"
                f"Original error: {e}"
            )
    else:
        lib_path = "libdwf.so"
        try:
            dwf = ctypes.cdll.LoadLibrary(lib_path)
        except OSError as e:
            raise DWFLoadError(
                f"Could not load '{lib_path}'.\n"
                "Please install WaveForms (includes Adept Runtime):\n"
                "  https://digilent.com/reference/software/waveforms/waveforms-3/start\n"
                f"Original error: {e}"
            )

    # --- load dwfconstants ---
    constants, constants_path = _find_dwfconstants()
    if constants is None:
        raise DWFLoadError(
            "Could not find dwfconstants.py.\n"
            "It is installed with WaveForms SDK.\n"
            "Expected locations:\n"
            "  macOS: /Applications/WaveForms.app/Contents/Resources/SDK/samples/py/\n"
            "  Linux: /usr/share/digilent/waveforms/samples/py/"
        )

    return dwf, constants, constants_path


def get_dwf_version(dwf) -> str:
    """Return the DWF library version string."""
    buf = ctypes.create_string_buffer(16)
    dwf.FDwfGetVersion(buf)
    return buf.value.decode("ascii", errors="replace")
