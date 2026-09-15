# Captura headless de pantallas 5250 (probe)

Herramienta del oráculo para capturar pantallas 5250 **sin abrir una ventana**,
usando el stack de **tn5250j** directamente (misma negociación telnet, query y
login que el emulador gráfico). Sirve para obtener el ground-truth visual de
pantallas de PUB400 o de iNative local: texto, posiciones y colores por celda.

## Por qué existe

El cliente TN5250 plano de `probe/colectores/display_5250.py` no puede hacer
login interactivo en PUB400 (bloqueado por `CPF1296 - Sign-on information
required`: la cuenta exige autenticación de terminal ACS/TIKTONE; ver
`documentacion/03-pantallas-fidelidad.md`). tn5250j sí completa el login porque
el `Session5250` negocia exactamente como el emulador. Este driver reutiliza ese
stack sin GUI y vuelca cada pantalla a texto.

## Componentes

- `CapturaHeadless.java` — sesión tn5250j headless: conecta, loguea y ejecuta
  los comandos indicados, imprimiendo cada pantalla (grid 24×80) con el color
  por celda (código del esquema tn5250j) y la lista de campos.
- `captura_headless.sh` — wrapper: lee `oracle.env` (raíz del repo), compila y
  ejecuta.
- `proxytls.go` — proxy pequeño plano→TLS que registra el tráfico 5250
  descifrado de PUB400 (necesario porque PUB400 usa el puerto 992 con TLS).

## Requisitos

- JDK (java/javac) y el jar de tn5250j (por defecto
  `~/Downloads/tn5250j-0.8.0-beta2-no-depedencies.jar`; sobreescribible con la
  variable `TN5250J_JAR`).
- `oracle.env` en la raíz del repo con `ORACLE_IBM_USER` / `ORACLE_IBM_PASSWORD`
  (el script usa `ORACLE_USER`/`ORACLE_PASS`, que rellena desde `oracle.env`).

## Uso

### Contra iNative local (puerto 5250, sin TLS)

```bash
./probe/tn5250j_headless/captura_headless.sh 127.0.0.1 5250 "STRPDM,WRKLIBPDM,WRKOBJ *ALL" /tmp/pdm_local.txt
```

### Contra PUB400 (vía proxy TLS)

```bash
# 1) Compilar el proxy y lanzarlo: escucha plano en 9992 → TLS a pub400:992
(cd probe/tn5250j_headless && go build -o /tmp/proxytls proxytls.go)
/tmp/proxytls 127.0.0.1:9992 pub400.com:992 /tmp/pub400_proxy.log &
# 2) Capturar a través del proxy
./probe/tn5250j_headless/captura_headless.sh 127.0.0.1 9992 "STRPDM,WRKLIBPDM,WRKOBJ *ALL,WRKMBRPDM FILE(QGPL/QRPGLESRC)" /tmp/pdm_pub400.txt
# 3) Detener el proxy
kill %1
```

`oracle.env` debe apuntar a los datos correctos
(`ORACLE_IBM_USER=C3S41`, `ORACLE_IBM_PASSWORD=...`).

## Salida

Para cada pantalla imprime:

```
### STRPDM  (24x80)
   |                       Gestor de desarrollo de programas (PDM)|
    colors: 7777...   <- código de color por celda (esquema tn5250j)
   fields: F0(19,6,len153)
```

Códigos de color internos de tn5250j (schema por defecto): `1`=azul/turquesa,
`2`=verde, `7`=blanco (los demás son variantes). Se usan para replicar el
aspecto en iNative (ver `documentacion/25-fidelidad-pantallas.md`).

## Referencias

- `../colectores/display_5250.py` — cliente plano (login bloqueado por CPF1296).
- `documentacion/03-pantallas-fidelidad.md` §CPF1296.
- `iNative/documentacion/25-fidelidad-pantallas.md` §Pantallas PDM (25 ago).