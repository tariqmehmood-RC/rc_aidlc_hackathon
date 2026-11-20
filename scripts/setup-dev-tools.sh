#!/usr/bin/env bash
# Installs the machine-level tools this project's checks and browser test need.
# They are binaries, not npm packages, so they cannot live in node_modules.
# Safe to re-run: each tool is skipped if the pinned version is already present.
#
#   gitleaks 8.30.1   used by `npm run scan:secrets`   -> ~/.local/bin/gitleaks
#   semgrep 1.186.0   used by `npm run scan:sast`      -> uv tool (own Python 3.12)
#   Google Chrome     used by the Playwright MCP server and scripts/browser-check.mjs
#
# Usage: bash scripts/setup-dev-tools.sh
set -euo pipefail

GITLEAKS_VERSION="8.30.1"
SEMGREP_VERSION="1.186.0"
BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}"

install_gitleaks() {
  if command -v gitleaks >/dev/null && [ "$(gitleaks version)" = "${GITLEAKS_VERSION}" ]; then
    echo "gitleaks ${GITLEAKS_VERSION} already installed"
    return
  fi
  local tmp archive base
  tmp="$(mktemp -d)"
  archive="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
  base="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}"
  curl -sSL -o "${tmp}/${archive}" "${base}/${archive}"
  curl -sSL -o "${tmp}/checksums.txt" "${base}/gitleaks_${GITLEAKS_VERSION}_checksums.txt"
  # Refuse to install unless the archive matches the published checksum.
  (cd "${tmp}" && grep " ${archive}\$" checksums.txt | sha256sum -c -)
  tar -xzf "${tmp}/${archive}" -C "${tmp}" gitleaks
  install -m 755 "${tmp}/gitleaks" "${BIN_DIR}/gitleaks"
  rm -rf "${tmp}"
  echo "installed gitleaks $(gitleaks version)"
}

install_semgrep() {
  if command -v semgrep >/dev/null &&
    [ "$(SEMGREP_SEND_METRICS=off semgrep --version --disable-version-check 2>/dev/null | tail -1)" = "${SEMGREP_VERSION}" ]; then
    echo "semgrep ${SEMGREP_VERSION} already installed"
    return
  fi
  # Semgrep needs Python 3.10+; uv supplies its own interpreter.
  uv tool install --force --python 3.12 "semgrep==${SEMGREP_VERSION}"
  echo "installed semgrep ${SEMGREP_VERSION}"
}

install_chrome() {
  if [ -x /opt/google/chrome/chrome ]; then
    echo "Google Chrome already installed: $(/opt/google/chrome/chrome --version 2>/dev/null | tail -1)"
    return
  fi
  # Playwright's own installer does not support Amazon Linux; use Google's RPM.
  sudo dnf install -y https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
}

install_gitleaks
install_semgrep
install_chrome
echo "done"
