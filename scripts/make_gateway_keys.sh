#!/usr/bin/env bash
# Creates a private key and a certificate signing request (CSR) for each zone gateway.
# - Private keys go to certs/ (ignored by Git) and never leave this machine.
# - CSRs go to infra/gateway-csrs/ (committed). They only contain the public key.
# Safe to re-run: existing keys and CSRs are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p infra/gateway-csrs
for zone in north east west; do
  dir="certs/gateway-$zone"
  csr="infra/gateway-csrs/gateway-$zone.csr"
  mkdir -p "$dir"

  if [ ! -f "$dir/private.pem.key" ]; then
    openssl ecparam -name prime256v1 -genkey -noout -out "$dir/private.pem.key"
    chmod 600 "$dir/private.pem.key"
    echo "Created private key for gateway-$zone"
  else
    echo "Kept existing private key for gateway-$zone"
  fi

  if [ ! -f "$csr" ]; then
    openssl req -new -key "$dir/private.pem.key" -subj "/CN=gateway-$zone" -out "$csr"
    echo "Created CSR for gateway-$zone"
  else
    echo "Kept existing CSR for gateway-$zone"
  fi
done
