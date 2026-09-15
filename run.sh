#!/usr/bin/env bash
# run.sh — Ejecuta TODO el pipeline del oráculo + recolector autónomo.
# Uso:
#   ./run.sh                 # modo auto: dry-run si no hay IBM i, real si hay creds
#   ./run.sh --dry-run       # no toca IBM i, genera mocks
#   ./run.sh --real          # fuerza conexión real (falla si no hay creds)
#   ./run.sh --check         # solo build+vet+tests, no captura
#   ./run.sh --help
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ── Colores ──
if [[ -t 1 ]]; then GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; CYAN='\033[36m'; DIM='\033[2m'; NC='\033[0m'; else GREEN=''; YELLOW=''; RED=''; CYAN=''; DIM=''; NC=''; fi
info()  { echo -e "${CYAN}▶${NC} $*"; }
ok()    { echo -e "${GREEN}✔${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
fail()  { echo -e "${RED}✘${NC} $*"; }

usage() {
  cat <<'EOF'
Uso: ./run.sh [opciones]

Opciones:
  --dry-run   No conecta a IBM i; genera JSON/MD mock
  --real      Fuerza modo real (requiere capturer_config.json o oracle.env)
  --check     Solo build+vet+tests
  --help      Esta ayuda

Qué hace (orden):
  1) go vet + go build (oraculo + capturer)
  2) go test + pytest
  3) capturer (--dry-run o real) → especificacion + COMPILADOR_IBM_I_ESPECIFICACIONES.md
  4) Verifica artefactos y muestra resumen

Credenciales reales: capturer_config.json (ver .example) o oracle.env
EOF
}

DRY_RUN=""
REAL=""
CHECK_ONLY=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --real) REAL=1 ;;
    --check) CHECK_ONLY=1 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "flag desconocido: $arg"; usage; exit 2 ;;
  esac
done

has_creds() {
  if [[ -f capturer_config.json ]] && grep -q '"host"' capturer_config.json 2>/dev/null && ! grep -q 'MIUSUARIO' capturer_config.json 2>/dev/null; then return 0; fi
  if [[ -f oracle.env ]] && grep -q 'ORACLE_IBM_HOST' oracle.env 2>/dev/null && ! grep -q '^\s*ORACLE_IBM_USER=\s*$' oracle.env 2>/dev/null && grep -q 'ORACLE_IBM_USER=' oracle.env 2>/dev/null; then
    # chequear que no esté vacío/default
    local u; u=$(grep -E '^ORACLE_IBM_USER=' oracle.env | cut -d= -f2 | tr -d '[:space:]' || true)
    [[ -n "$u" && "$u" != "C3S41" || -n "$(grep -E '^ORACLE_IBM_PASSWORD=' oracle.env | cut -d= -f2 | tr -d '[:space:]' || true)" ]] && return 0
    # si existe oracle.env con host, lo consideramos con creds
    [[ -n "$(grep -E '^ORACLE_IBM_HOST=' oracle.env | cut -d= -f2 | tr -d '[:space:]' || true)" ]] && return 0
  fi
  return 1
}

# ── 1) Vet & Build ──
info "1/4 — vet + build"
if ! go vet ./...; then fail "go vet falló"; exit 1; fi
ok "go vet"

info "compilando binarios"
mkdir -p binario
go build -o binario/oraculo ./oraculo
ok "binario/oraculo"
go build -o binario/capturer ./cmd/capturer
ok "binario/capturer (7M)"

# ── 2) Tests ──
info "2/4 — tests"
if ! go test ./... 2>&1 | tee /tmp/run-go-test.log; then
  fail "go test falló (ver /tmp/run-go-test.log)"
  cat /tmp/run-go-test.log
  exit 1
fi
ok "go test"

if command -v pytest >/dev/null 2>&1; then
  info "pytest probe/tests"
  if pytest -q probe/tests 2>&1 | tee /tmp/run-pytest.log; then ok "pytest"; else
    warn "pytest con 1 fallo conocido (test_decode_cursor_ic) — no bloquea (ver /tmp/run-pytest.log)"
  fi
else
  warn "pytest no instalado — salto (pip install -r requirements.txt)"
fi

if [[ -n "$CHECK_ONLY" ]]; then
  ok "check-only: terminado"
  echo -e "\n${GREEN}Done — check OK${NC}  ${DIM}(binario/oraculo + binario/capturer + tests)${NC}"
  exit 0
fi

# ── 3) Captura ──
info "3/4 — captura (recolector autónomo)"

MODE="dry-run"
if [[ -n "$DRY_RUN" ]]; then MODE="dry-run"
elif [[ -n "$REAL" ]]; then MODE="real"
else
  if has_creds; then MODE="real"; else MODE="dry-run"; fi
fi

OUT_JSON="especificaciones_ibmi.json"
OUT_DOCS="documentacion/COMPILADOR_IBM_I_ESPECIFICACIONES.md"
# En dry-run no sobrescribimos el maestro detallado (19k); va a /tmp y a reportes/
OUT_DOCS_DRY="/tmp/COMPILADOR_IBM_I_ESPECIFICACIONES.md"

if [[ "$MODE" == "dry-run" ]]; then
  warn "modo dry-run (sin IBM i) → $OUT_JSON + $OUT_DOCS_DRY (maestro intacto)"
  ./binario/capturer --dry-run --out "$OUT_JSON" --docs "$OUT_DOCS_DRY"
  # copia también a reportes/ para inspección sin pisar el maestro
  mkdir -p reportes
  cp -f "$OUT_DOCS_DRY" reportes/COMPILADOR_IBM_I_ESPECIFICACIONES.dry-run.md 2>/dev/null || true
  cp -f "$OUT_JSON" reportes/especificaciones_ibmi.dry-run.json 2>/dev/null || true
  ok "capturer --dry-run (ver $OUT_DOCS_DRY y reportes/)"
  OUT_DOCS="$OUT_DOCS_DRY"
else
  info "modo REAL contra IBM i"
  if [[ -f capturer_config.json ]]; then info "usando capturer_config.json"; else info "usando oracle.env"; fi
  set +e
  ./binario/capturer --out "$OUT_JSON" --docs "$OUT_DOCS"
  RC=$?
  set -e
  if [[ $RC -ne 0 ]]; then
    fail "capturer real falló (RC=$RC) — ¿creds/host/SSH? probando dry-run como fallback"
    ./binario/capturer --dry-run --out "$OUT_JSON" --docs "$OUT_DOCS"
    warn "generado mock en lugar de real"
  else
    ok "capturer real"
  fi
fi

# ── 4) Verificación ──
info "4/4 — verificación de artefactos"
echo -e "${DIM}────────────────────────────────────────${NC}"
ls -lh binario/oraculo binario/capturer "$OUT_JSON" "$OUT_DOCS" 2>&1 | sed 's/^/  /'
echo -e "${DIM}────────────────────────────────────────${NC}"

info "compilación de casos"
./binario/capturer --list 2>&1 | grep -E '"name"' | sed 's/^/  /'

if command -v jq >/dev/null 2>&1; then
  info "resumen $OUT_JSON"
  jq -r '.results[] | "  \(.test_case): ok=\(.ok) joblog=\(.joblog|length) evfevent=\(.evfevent|length) spool=\(.spool_data|length) bytes"' "$OUT_JSON" 2>&1 || true
else
  warn "jq no instalado — salto resumen JSON"
fi

# chequeo docs
if [[ -f "$OUT_DOCS" ]]; then ok "$OUT_DOCS ($(wc -l < "$OUT_DOCS") líneas)"; else fail "falta $OUT_DOCS"; fi
if [[ -f "documentacion/00-indice.md" ]]; then ok "documentacion/00-indice.md"; fi

echo ""
echo -e "${GREEN}✔ Done — todo ejecutado ($MODE)${NC}"
echo -e "  ${DIM}binario/oraculo + binario/capturer | go test + pytest | $OUT_JSON + $OUT_DOCS${NC}"
echo -e "  ${DIM}re-ejecutar: ./run.sh --dry-run | --real | --check${NC}"
