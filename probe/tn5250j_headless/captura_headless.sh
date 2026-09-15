#!/usr/bin/env bash
# Captura headless de pantallas 5250 usando el stack de tn5250j, sin ventana.
# Lee credenciales de oracle.env (a nivel repositorio) y compila/ejecuta
# CapturaHeadless.java contra el host/puerto indicado.
#
# Uso:
#   ./captura_headless.sh <host> <puerto> [cmdsCsv] [salida.txt]
#
# Ejemplos:
#   # Contra iNative local:
#   ./captura_headless.sh 127.0.0.1 5250 "STRPDM,WRKLIBPDM" /tmp/pdm_local.txt
#
#   # Contra PUB400 vía proxy TLS (ver README.md):
#   ./proxytls 127.0.0.1:9992 pub400.com:992 /tmp/pdm_proxy.log &
#   ./captura_headless.sh 127.0.0.1 9992 "STRPDM,WRKLIBPDM" /tmp/pdm_pub400.txt
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"

# tn5250j jar (necesario): TN5250J_JAR o ruta por defecto
TN5250J_JAR="${TN5250J_JAR:-}"
if [ -z "$TN5250J_JAR" ]; then
  if [ -f "/home/cesar/Downloads/tn5250j-0.8.0-beta2-no-depedencies.jar" ]; then
    TN5250J_JAR="/home/cesar/Downloads/tn5250j-0.8.0-beta2-no-depedencies.jar"
  else
    echo "TN5250J_JAR no configurado (apunta al jar de tn5250j)" >&2
    exit 2
  fi
fi

# Credenciales: respetan ORACLE_USER/ORACLE_PASS del entorno; si no vienen,
# se toman de oracle.env (ORACLE_IBM_USER / ORACLE_IBM_PASSWORD).
if [ -z "${ORACLE_USER:-}" ] || [ -z "${ORACLE_PASS:-}" ]; then
  if [ -f "$REPO/oracle.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO/oracle.env"
    set +a
  fi
  : "${ORACLE_USER:=C3S41}"
  : "${ORACLE_PASS:=matica96}"
fi
export ORACLE_USER ORACLE_PASS

HOST="${1:?host requerido}"
PORT="${2:?puerto requerido}"
CMDS="${3:-STRPDM,WRKLIBPDM,WRKOBJ *ALL,WRKMBRPDM FILE(QGPL/QRPGLESRC)}"
OUT="${4:-}"

cd "$DIR"
javac -cp "$TN5250J_JAR" CapturaHeadless.java
if [ -n "$OUT" ]; then
  java -cp ".:$TN5250J_JAR" CapturaHeadless "$HOST" "$PORT" "$CMDS" "$OUT"
  echo "Captura escrita en: $OUT" >&2
else
  java -cp ".:$TN5250J_JAR" CapturaHeadless "$HOST" "$PORT" "$CMDS"
fi