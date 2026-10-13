#!/usr/bin/env bash
# Download the pinned Collector, otelcol-contrib 0.162.0, into
# .native/bin for the Chapter 10 labs, which run it without Docker:
#
#   scripts/fetch_collector.sh
#   uv run python scripts/fs15_sampling_blind_spot.py
#
# Each archive's SHA-256 below was computed from the v0.162.0 release
# archives on 2026-10-13. An archive with any other hash is refused
# and nothing is installed. On Windows, run the labs under WSL.
set -euo pipefail
VERSION="0.162.0"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${BIN:-$ROOT/.native/bin}"
RELEASES="https://github.com/open-telemetry/opentelemetry-collector-releases"

case "$(uname -s)" in
  Linux) os=linux ;;
  Darwin) os=darwin ;;
  *) echo "no pinned Collector for $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64 | amd64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "no pinned Collector for $(uname -m)" >&2; exit 1 ;;
esac

# Bash 3.2 (macOS) has no associative arrays, hence the case.
case "${os}_${arch}" in
  linux_amd64)
    want=fcc063749f730f8c21fe29f2d340ff174f5f1c5885bd3156fb6c985a3036fcc3 ;;
  linux_arm64)
    want=ecf6a917e2b53beb1703b19a84bc4e112a2fcaba549639cf6b0ba58446bfd7d2 ;;
  darwin_amd64)
    want=91a6e7a0f5e1981986c897db4535de5ba8d7fc45d4205809aecb9ebebf68c71c ;;
  darwin_arm64)
    want=d5e11974d2e4adac3cc001a25137aad52f6e77ec3034ba7735cac7c219a5f97a ;;
esac

target="$BIN/otelcol-contrib"
if [[ -x "$target" ]] && "$target" --version | grep -q " $VERSION\$"
then
  echo "already installed: $("$target" --version)"
  exit 0
fi

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
name="otelcol-contrib_${VERSION}_${os}_${arch}.tar.gz"
echo "downloading $name"
curl -fsSL --retry 3 -o "$work/$name" \
  "$RELEASES/releases/download/v$VERSION/$name"

got="$(sha256 "$work/$name")"
if [[ "$got" != "$want" ]]; then
  echo "refused: $name has SHA-256 $got" >&2
  echo "         the pinned value is $want" >&2
  exit 1
fi

# Extract the one binary into the empty work folder, then install.
mkdir "$work/out"
tar -xzf "$work/$name" -C "$work/out" otelcol-contrib
mkdir -p "$BIN"
install -m 0755 "$work/out/otelcol-contrib" "$target"
echo "installed: $("$target" --version)"
