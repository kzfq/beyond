#!/usr/bin/env bash
# Beyond one-line installer (Linux / macOS / Termux).
#   curl -fsSL https://raw.githubusercontent.com/kzfq/beyond/main/install.sh | bash
# Detects your OS, installs anything missing, clones Beyond, writes the config,
# installs the Python deps, and starts the agent (prints your link + password).
set -e

REPO="https://github.com/kzfq/beyond"
ENROLL_KEY="zySlnMP0DRHwAz6Ax0Y2doZ6bTaDB_HNRF0N1PT_AK0"
DIR="${BEYOND_DIR:-$HOME/beyond}"

say() { printf "\n\033[1;35m[beyond]\033[0m %s\n" "$1"; }

# --- Termux (Android): bounce into an Ubuntu proot so pip wheels work ---
if [ -n "$PREFIX" ] && printf '%s' "$PREFIX" | grep -q com.termux; then
  say "Termux detected — setting up an Ubuntu container (needed on Android)…"
  pkg install -y proot-distro >/dev/null 2>&1 || pkg install -y proot-distro
  proot-distro install ubuntu >/dev/null 2>&1 || true
  proot-distro login ubuntu -- bash -c \
    "apt-get update -y && apt-get install -y curl && curl -fsSL $REPO/raw/main/install.sh | bash"
  exit 0
fi

# --- detect package manager ---
PKG=""
if command -v apt-get >/dev/null 2>&1; then PKG=apt
elif command -v dnf >/dev/null 2>&1; then PKG=dnf
elif command -v pacman >/dev/null 2>&1; then PKG=pacman
elif command -v brew >/dev/null 2>&1; then PKG=brew
fi
SUDO=""
[ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO=sudo

pkgi() {
  case "$PKG" in
    apt) $SUDO apt-get update -y; $SUDO apt-get install -y "$@";;
    dnf) $SUDO dnf install -y "$@";;
    pacman) $SUDO pacman -Sy --noconfirm "$@";;
    brew) brew install "$@";;
  esac
}

say "Installing git + python…"
case "$PKG" in
  apt) pkgi git python3 python3-pip python3-venv curl;;
  dnf) pkgi git python3 python3-pip curl;;
  pacman) pkgi git python python-pip curl;;
  brew) pkgi git python;;
  *) say "No known package manager — ensure git and python3 are installed.";;
esac

PYBIN="$(command -v python3 || command -v python || true)"
[ -z "$PYBIN" ] && { say "Python not found. Install Python 3.10+ and re-run."; exit 1; }

# --- clone / update ---
if [ -d "$DIR/.git" ]; then
  say "Updating existing install…"; git -C "$DIR" pull --ff-only || true
else
  say "Cloning Beyond…"; git clone "$REPO" "$DIR"
fi
cd "$DIR"

# --- config (only if not already enrolled) ---
if [ ! -f backend/agent_config.json ]; then
  say "Writing config…"
  cat > backend/agent_config.json <<EOF
{
  "relay_base": "https://agent.selfbot.fyi",
  "viewer_base": "https://selfbot.fyi",
  "enroll_key": "$ENROLL_KEY",
  "slug": "",
  "agent_secret": "",
  "viewer_password": ""
}
EOF
fi

# --- python deps (use wheels; only build from source if wheels are missing) ---
export SODIUM_INSTALL=system
pipi() { "$PYBIN" -m pip install "$@" --break-system-packages 2>/dev/null || "$PYBIN" -m pip install "$@"; }

say "Upgrading pip…"; pipi --upgrade pip || true
say "Installing Python dependencies (may take a few minutes)…"
if ! pipi -r backend/requirements.txt; then
  say "Prebuilt packages unavailable — installing a build toolchain and retrying…"
  case "$PKG" in
    apt) pkgi build-essential pkg-config libjpeg-dev libpng-dev zlib1g-dev libssl-dev libsodium-dev;;
    dnf) pkgi gcc gcc-c++ make libjpeg-turbo-devel libpng-devel zlib-devel openssl-devel libsodium-devel;;
    pacman) pkgi base-devel libjpeg-turbo libpng zlib openssl libsodium;;
    brew) pkgi jpeg libpng libsodium openssl;;
  esac
  curl -fsSL https://sh.rustup.rs | sh -s -- -y
  . "$HOME/.cargo/env" 2>/dev/null || true
  pipi -r backend/requirements.txt
fi

say "Starting Beyond — your link + password appear below. Keep this running."
exec "$PYBIN" backend/beyond_agent.py
