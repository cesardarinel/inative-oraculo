.PHONY: help build test vet lint clean version pip captura captura-all

APP ?= oraculo
VERSION ?= v0.0.1
WP ?= python3
FIXTURE ?= conformance/dspf/HOLA-5250-001.json
OUT ?= esperado
# Compat: F= fixture, N= nombre (legado)
F ?=
N ?=

help: ## Muestra esta ayuda
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build: ## Compila el binario oraculo en ./binario
	go build -o binario/$(APP) ./oraculo

build-capturer: ## Compila el recolector autónomo (plan vscode.md)
	go build -o binario/capturer ./cmd/capturer

capturer: build-capturer ## Ejecuta el recolector (usa capturer_config.json o oracle.env)
	./binario/capturer --out especificaciones_ibmi.json --docs documentacion/COMPILADOR_IBM_I_ESPECIFICACIONES.md

capturer-dry: build-capturer ## Ejecuta el recolector en modo mock (sin IBM i)
	./binario/capturer --dry-run --out /tmp/especificaciones_ibmi.json --docs /tmp/COMPILADOR_IBM_I_ESPECIFICACIONES.md && echo "mock OK" && ls -lh /tmp/especificaciones_ibmi.json

test: ## Ejecuta todas las pruebas (Go + Python si disponible)
	go test ./...
	@if command -v pytest >/dev/null 2>&1; then pytest -q probe/tests 2>/dev/null || echo " (pytest sin tests)"; else echo "pytest no instalado, solo go test"; fi

vet: ## Análisis estático
	go vet ./...

lint: vet ## Alias de estilo (por ahora go vet)

pip: ## Instala dependencias Python del oráculo
	pip install -r requirements.txt

captura: ## Captura un fixture contra IBM i (ej: make captura FIXTURE=conformance/dspf/HOLA-5250-001.json OUT=esperado)
	@if [ -n "$(F)" ]; then \
		if echo "$(F)" | grep -q "\.json$$"; then \
			$(WP) -m probe.captura --fixture $(F) --out $(OUT); \
		else \
			$(WP) -m probe.captura --fixture $(F) --out $(OUT); \
		fi; \
	elif [ -n "$(FIXTURE)" ]; then \
		$(WP) -m probe.captura --fixture $(FIXTURE) --out $(OUT); \
	else \
		echo "uso: make captura FIXTURE=conformance/dspf/HOLA-5250-001.json [OUT=esperado]"; \
		echo "  compat: make captura F=conformance/dspf/HOLA-5250-001.json N=HOLA"; \
		exit 2; \
	fi

captura-all: ## Captura todos los fixtures JSON en conformance/
	@for f in $$(find conformance -name "*.json" -type f 2>/dev/null); do \
		echo "=== $$f ==="; \
		$(WP) -m probe.captura --fixture $$f --out $(OUT) || echo "  fallo: $$f"; \
	done

captura-headless: ## Captura pantallas 5250 con tn5250j headless (HOST PORT [CMDS CSV] [OUT])
	@if [ -z "$(HOST)" ] || [ -z "$(PORT)" ]; then \
		echo "uso: make captura-headless HOST=127.0.0.1 PORT=5250 CMDS=\"STRPDM,WRKLIBPDM\" OUT=/tmp/pdm.txt"; \
		exit 2; \
	fi; \
	./probe/tn5250j_headless/captura_headless.sh $(HOST) $(PORT) "$(CMDS)" $(OUT)

proxy-tls: ## Compila el proxy plano→TLS para capturar PUB400 (992)
	cd probe/tn5250j_headless && go build -o binario/proxytls proxytls.go

clean: ## Elimina artefactos de compilación
	rm -rf binario dist probe/snapshots

version: build ## Muestra la versión
	./binario/$(APP) version

diff: build ## Compara expected vs actual (ej: make diff E=esperado/X.json A=actual/X.json F=conformance/dspf/HOLA-5250-001.json)
	./binario/$(APP) diff --fixture $(F) --expected $(E) --actual $(A) $(ARGS)

# JobLog Recorder — Record & Replay (plan §20-§23)
joblog-record: ## Record JobLog contra IBM i (ej: make joblog-record ID=JOBLOG-0001 CMD="CALL PGM(QTEMP/X)")
	$(WP) -m probe.joblog_recorder record --id $(ID) --name "$(NAME)" --language "$(LANG)" --command "$(CMD)" --category "$(CAT)"

joblog-replay: ## Replay JobLog sin IBM i (ej: make joblog-replay ID=JOBLOG-0001)
	$(WP) -m probe.joblog_recorder replay $(ID)

joblog-list: ## Lista matriz de experimentos JobLog
	$(WP) -m probe.joblog_recorder list

joblog-matrix: ## Captura matriz smoke JobLog (requiere IBM i)
	$(WP) -m probe.joblog_recorder record-matrix

joblog-test: build ## Contract tests JobLog (§19)
	go test ./internal/joblog -v
