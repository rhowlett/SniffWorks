#!/usr/bin/env bash
# =============================================================================
# install.sh — AD2 I2C Tool installer (macOS + Ubuntu 22.04+)
# Installs into $SHARED_VENV when set (one venv shared by all projects),
# otherwise creates a .venv in the script's directory. Installs PySide6.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SHARED_VENV:-$SCRIPT_DIR/.venv}"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

# ─── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[OK]${NC}    $*"; }
warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ─── header ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLU}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLU}║          AD2 I2C / SMBus Tool — Installer           ║${NC}"
echo -e "${BLU}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── OS detection ─────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macOS" ;;
    Linux)  PLATFORM="Linux"  ;;
    *)      error "Unsupported OS: $OS (Windows not supported by this script)" ;;
esac
info "Platform: $PLATFORM"

# ─── Find Python 3 ────────────────────────────────────────────────────────────
find_python() {
    for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
            minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
            # Accept if major > min, or (major == min and minor >= min_minor)
            if [[ "$major" -gt "$PYTHON_MIN_MAJOR" ]] || \
               { [[ "$major" -eq "$PYTHON_MIN_MAJOR" ]] && [[ "$minor" -ge "$PYTHON_MIN_MINOR" ]]; }; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(find_python || true)

# ─── Auto-provision Python 3.10+ if the system only has older Python ──────────
if [[ -z "$PYTHON" ]]; then
    echo ""
    warn "No Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ interpreter found on this system."
    echo ""
    echo "  A virtual environment can only be the same version as the Python that"
    echo "  creates it, so a ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ interpreter must exist first."
    echo "  (macOS ships only Python 3.9, whose pip cannot install the PySide6 wheel.)"
    echo ""

    if [[ "$PLATFORM" == "macOS" ]]; then
        read -r -p "  Install Python 3.12 automatically via Homebrew now? [Y/n] " resp
        resp="${resp:-Y}"
        if [[ ! "$resp" =~ ^[Yy]$ ]]; then
            error "Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ required. Install it and re-run install.sh
  brew install python@3.12   (or download from https://www.python.org/downloads/macos/)"
        fi

        # Ensure Homebrew is available
        if ! command -v brew &>/dev/null; then
            warn "Homebrew not found — installing it first (you may be prompted for your password)…"
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add brew to PATH for this session (Apple Silicon vs Intel)
            if [[ -x /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -x /usr/local/bin/brew ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
        fi
        command -v brew &>/dev/null || error "Homebrew installation failed. Install Python 3.12 manually and re-run."

        info "Installing python@3.12 via Homebrew…"
        brew install python@3.12

        # Re-resolve PATH so the new python3.12 is visible this session
        if [[ -x /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -x /usr/local/bin/brew ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        hash -r

    elif [[ "$PLATFORM" == "Linux" ]]; then
        read -r -p "  Install Python 3, venv and pip via apt now (sudo)? [Y/n] " resp
        resp="${resp:-Y}"
        if [[ ! "$resp" =~ ^[Yy]$ ]]; then
            error "Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ required. Install it and re-run install.sh
  sudo apt install python3 python3-venv python3-pip"
        fi
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip
        hash -r
    fi

    # Try again after provisioning
    PYTHON=$(find_python || true)
    if [[ -z "$PYTHON" ]]; then
        error "Still no Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ after install attempt.
Open a new terminal (so PATH refreshes) and re-run install.sh, or install Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ manually."
    fi
    ok "Provisioned Python: $PYTHON"
fi

PYVER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
ok "Python found: $PYTHON  ($PYVER)"

# ─── Linux: check system packages ─────────────────────────────────────────────
if [[ "$PLATFORM" == "Linux" ]]; then
    info "Checking for python3-venv and libGL (needed by PySide6)…"

    MISSING_PKGS=()
    if ! "$PYTHON" -c "import venv" 2>/dev/null; then
        MISSING_PKGS+=("python3-venv")
    fi
    # Check libGL for Qt/PySide6
    if ! ldconfig -p 2>/dev/null | grep -q libGL.so.1; then
        MISSING_PKGS+=("libgl1")
    fi
    # libxkbcommon for PySide6 QPA
    if ! ldconfig -p 2>/dev/null | grep -q libxkbcommon.so; then
        MISSING_PKGS+=("libxkbcommon0")
    fi

    if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
        warn "Missing system packages: ${MISSING_PKGS[*]}"
        echo ""
        echo "  Run:  sudo apt install ${MISSING_PKGS[*]}"
        echo ""
        read -r -p "  Attempt to install them now with sudo? [y/N] " resp
        if [[ "$resp" =~ ^[Yy]$ ]]; then
            sudo apt-get install -y "${MISSING_PKGS[@]}"
        else
            error "Please install the packages above first, then re-run install.sh"
        fi
    fi
fi

# ─── WaveForms SDK check ───────────────────────────────────────────────────────
echo ""
info "Checking for Digilent WaveForms SDK / DWF library…"

DWF_FOUND=false
if [[ "$PLATFORM" == "macOS" ]]; then
    if [[ -f "/Library/Frameworks/dwf.framework/dwf" ]]; then
        ok "DWF library found at /Library/Frameworks/dwf.framework/dwf"
        DWF_FOUND=true
    fi
else
    if ldconfig -p 2>/dev/null | grep -q libdwf.so; then
        ok "libdwf.so found in system library paths"
        DWF_FOUND=true
    elif [[ -f "/usr/lib/libdwf.so" ]] || [[ -f "/usr/local/lib/libdwf.so" ]]; then
        ok "libdwf.so found"
        DWF_FOUND=true
    fi
fi

if [[ "$DWF_FOUND" == "false" ]]; then
    warn "WaveForms SDK / DWF library NOT found!"
    echo ""
    echo "  The app will still install, but AD2 won't be accessible until you install WaveForms."
    echo ""
    if [[ "$PLATFORM" == "macOS" ]]; then
        echo "  Download: https://digilent.com/shop/software/digilent-waveforms/"
        echo "  Install the .dmg — this installs the DWF framework."
    else
        echo "  Download the .deb from: https://digilent.com/reference/software/waveforms/waveforms-3/start"
        echo "  Install: sudo dpkg -i digilent.waveforms_*.deb"
        echo "  Also need Adept Runtime: https://digilent.com/reference/software/adept/start"
    fi
    echo ""
fi

# ─── dwfconstants.py check ────────────────────────────────────────────────────
CONST_FOUND=false
if [[ "$PLATFORM" == "macOS" ]]; then
    CONST_PATH="/Applications/WaveForms.app/Contents/Resources/SDK/samples/py/dwfconstants.py"
else
    CONST_PATH="/usr/share/digilent/waveforms/samples/py/dwfconstants.py"
fi

if [[ -f "$CONST_PATH" ]]; then
    ok "dwfconstants.py found at $CONST_PATH"
    cp "$CONST_PATH" "$SCRIPT_DIR/" && info "Copied dwfconstants.py into app folder"
    CONST_FOUND=true
else
    warn "dwfconstants.py not found at $CONST_PATH"
    # Look for it anywhere
    FOUND_PATH=$(find /Applications /usr/share /usr/local 2>/dev/null -name dwfconstants.py -maxdepth 8 | head -1 || true)
    if [[ -n "$FOUND_PATH" ]]; then
        ok "dwfconstants.py found at $FOUND_PATH — copying to app directory"
        cp "$FOUND_PATH" "$SCRIPT_DIR/"
        CONST_FOUND=true
    else
        warn "dwfconstants.py not found. Install WaveForms SDK first."
    fi
fi

# ─── Create virtual environment ───────────────────────────────────────────────
echo ""
info "Creating virtual environment at $VENV_DIR …"

if [[ -n "${SHARED_VENV:-}" && -x "$VENV_DIR/bin/python" ]]; then
    # Shared venv is used by other projects — never delete it, just add to it.
    ok "Re-using shared virtual environment"
else
    if [[ -d "$VENV_DIR" ]]; then
        warn ".venv already exists — recreating…"
        rm -rf "$VENV_DIR"
    fi
    "$PYTHON" -m venv "$VENV_DIR"
    ok "Virtual environment created"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# ─── Upgrade pip ──────────────────────────────────────────────────────────────
info "Upgrading pip…"
pip install --upgrade pip --quiet

# ─── Install dependencies ─────────────────────────────────────────────────────
info "Installing Python dependencies from requirements.txt…"
# --no-compile: PySide6 wheels bundle Jinja2 template files (*.tmpl.py) that are
# NOT valid Python. pip's post-install byte-compile step chokes on them (and on
# Python 3.9 the error handler itself crashes). Skipping compile avoids this
# entirely; .pyc files are generated lazily at runtime with no downside.
pip install --no-compile -r "$SCRIPT_DIR/requirements.txt"
ok "Dependencies installed"

# ─── Verify the install actually imports ──────────────────────────────────────
info "Verifying PySide6 import…"
if python3 -c "import PySide6.QtWidgets; print('PySide6', PySide6.__version__)" 2>/dev/null; then
    ok "PySide6 imports correctly"
else
    error "PySide6 installed but failed to import. On Linux try: sudo apt install libgl1 libxkbcommon0"
fi

# ─── Create launch script ─────────────────────────────────────────────────────
LAUNCH_SCRIPT="$SCRIPT_DIR/run.sh"
cat > "$LAUNCH_SCRIPT" << 'LAUNCH_EOF'
#!/usr/bin/env bash
# run.sh — launch an ion_i2c_tool app inside the project venv.
# Uses $SHARED_VENV when set, otherwise the .venv next to this script.
# Usage: ./run.sh sniffer_ion.py [args...]      (default: sniffer_ion.py)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SHARED_VENV:-$SCRIPT_DIR/.venv}"

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
    echo "error: $VENV_DIR not found — run ./install.sh first" >&2
    exit 1
fi
source "$VENV_DIR/bin/activate"

APP="${1:-sniffer_ion.py}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ ! -f "$SCRIPT_DIR/$APP" ]]; then
    echo "error: $APP not found in $SCRIPT_DIR" >&2
    exit 1
fi
exec python3 "$SCRIPT_DIR/$APP" "$@"
LAUNCH_EOF
chmod +x "$LAUNCH_SCRIPT"
ok "Launch script created: $LAUNCH_SCRIPT"

# ─── macOS: offer to create an app shortcut ───────────────────────────────────
# TODO
#if [[ "$PLATFORM" == "macOS" ]]; then
    #APPDIR="$HOME/Applications/AD2 I2C Tool.app"
    #mkdir -p "$APPDIR/Contents/MacOS"
    #cat > "$APPDIR/Contents/MacOS/AD2 I2C Tool" << MACOS_EOF
##!/usr/bin/env bash
#source "${VENV_DIR}/bin/activate"
#exec python "${SCRIPT_DIR}/main.py"
#MACOS_EOF
    #chmod +x "$APPDIR/Contents/MacOS/AD2 I2C Tool"
    #cat > "$APPDIR/Contents/Info.plist" << 'PLIST_EOF'
#<?xml version="1.0" encoding="UTF-8"?>
#<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
#<plist version="1.0">
#<dict>
    #<key>CFBundleExecutable</key>  <string>AD2 I2C Tool</string>
    #<key>CFBundleName</key>        <string>AD2 I2C Tool</string>
    #<key>CFBundleIdentifier</key>  <string>com.ad2-i2c-tool.app</string>
    #<key>CFBundleVersion</key>     <string>1.0.0</string>
    #<key>CFBundleShortVersionString</key> <string>1.0.0</string>
    #<key>LSMinimumSystemVersion</key>    <string>11.0</string>
    #<key>NSHighResolutionCapable</key>   <true/>
#</dict>
#</plist>
#PLIST_EOF
    #ok "macOS app bundle created: $APPDIR"
#fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GRN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║               Installation Complete ✓               ║${NC}"
echo -e "${GRN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Launch the app:"
echo "    $LAUNCH_SCRIPT"
echo ""
if [[ "$DWF_FOUND" == "false" ]]; then
    echo -e "${YLW}  ⚠ Install WaveForms SDK to use with AD2 hardware.${NC}"
    echo ""
fi
echo "  Or activate the venv and run directly:"
echo "    source $VENV_DIR/bin/activate"
echo "    python3 $SCRIPT_DIR/sniffer_ion.py"
echo ""
