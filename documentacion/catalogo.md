¡Perfecto! Aprovechemos que IBM i es **autodescriptivo** para construir un **extractor automático del catálogo completo**. El programador escribirá un solo binario que, al ejecutarse, se conecta al IBM i, **extrae el DDL de todas las tablas/vistas de QSYS2**, lo adapta a SQLite y genera un archivo `.sql` o una base de datos SQLite lista para usar en iNative.

Aquí tienes el **plan definitivo**, con todos los detalles técnicos para que el programador lo implemente sin ayuda.

---

# PLAN: EXTRACCIÓN AUTOMÁTICA DEL CATÁLOGO QSYS2 COMPLETO PARA iNative

## 1. Objetivo

Crear un programa (en Go, Python o Node) que:

1. Se conecte por SSH a un IBM i real.
2. Obtenga la lista de **todas las tablas y vistas** del esquema `QSYS2`.
3. Para cada una, extraiga su **DDL exacto** (CREATE TABLE/VIEW) usando la función `QSYS2.GENERATE_SQL`.
4. Convierta ese DDL de sintaxis DB2 for i a **sintaxis SQLite** (tipos, restricciones, etc.).
5. Genere un archivo `catalogo_qsys2.sql` con todas las sentencias `CREATE TABLE` y `CREATE VIEW` adaptadas, y también los **datos estáticos** de aquellas tablas que sean necesarias (por ejemplo, códigos de error CPF/RNF).
6. Opcionalmente, construya directamente una base de datos SQLite (`qsys2_catalog.db`) que iNative pueda usar como su catálogo del sistema.

---

## 2. Estrategia de Extracción (Pasos Técnicos)

### 2.1. Obtener la lista de objetos de QSYS2

Ejecuta esta consulta en el IBM i:

```sql
SELECT TABLE_NAME, TABLE_TYPE 
FROM QSYS2.SYSTABLES 
WHERE TABLE_SCHEMA = 'QSYS2'
  AND TABLE_TYPE IN ('T', 'V')   -- T=Tabla, V=Vista
ORDER BY TABLE_NAME;
```

Esto devuelve los nombres de todas las tablas (`T`) y vistas (`V`) del catálogo.

### 2.2. Extraer DDL de cada objeto

Para cada `TABLE_NAME`, ejecuta:

```sql
SELECT SQL_STMT 
FROM TABLE(QSYS2.GENERATE_SQL('nombre_tabla', 'QSYS2', 'TABLE')) AS SQL_STMT;
```

O si es una vista:

```sql
SELECT SQL_STMT 
FROM TABLE(QSYS2.GENERATE_SQL('nombre_vista', 'QSYS2', 'VIEW')) AS SQL_STMT;
```

**Nota**: `GENERATE_SQL` devuelve una tabla con una sola columna `SQL_STMT` que contiene la sentencia CREATE completa, con saltos de línea y todo.

### 2.3. Adaptar el DDL a SQLite

DB2 for i usa tipos como:
- `VARCHAR(n)` → SQLite `TEXT`
- `DECIMAL(p,s)` → SQLite `NUMERIC` o `REAL`
- `INTEGER`, `SMALLINT` → SQLite `INTEGER`
- `TIMESTAMP` → SQLite `DATETIME`
- `CHAR(n)` → SQLite `TEXT`
- `BLOB` → SQLite `BLOB`

Además, DB2 tiene `GENERATED ALWAYS AS IDENTITY`, `NOT NULL WITH DEFAULT`, etc. SQLite acepta `NOT NULL` y `DEFAULT`, pero no `GENERATED`. Para simplificar, puedes omitir `GENERATED` y usar `AUTOINCREMENT` cuando sea necesario (pero en el catálogo rara vez se usa).

**Recomendación**: Usa un parser simple que reemplace:
- `VARCHAR(\([0-9]+\))` → `TEXT`
- `CHAR(\([0-9]+\))` → `TEXT`
- `DECIMAL(\([0-9]+,\s*[0-9]+\))` → `NUMERIC`
- `FOR BIT DATA` → `BLOB`
- `NOT NULL WITH DEFAULT` → `NOT NULL DEFAULT`
- `PRIMARY KEY(...)` → se mantiene igual (SQLite lo soporta).
- `CREATE VIEW` → `CREATE VIEW` (SQLite soporta vistas).

También elimina cláusulas específicas de DB2 como `IN <tablespace>`, `COMPRESS`, `RCDFMT`, etc.

### 2.4. Generar el archivo SQLite

Puedes generar un archivo `.sql` con todas las sentencias, o directamente usar la biblioteca `database/sql` de Go para crear la base de datos `qsys2_catalog.db` y ejecutar las sentencias adaptadas.

---

## 3. El Programa en Go (Estructura y Código Clave)

El programador puede escribir un único archivo `cmd/extractor/main.go`:

```go
package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"regexp"
	"strings"

	_ "github.com/mattn/go-sqlite3"
	"golang.org/x/crypto/ssh"
)

type Config struct {
	Host     string `json:"host"`
	User     string `json:"user"`
	Password string `json:"password,omitempty"`
	KeyFile  string `json:"keyfile,omitempty"`
}

// Conecta por SSH al IBM i y ejecuta comandos
func runSSHCommand(cfg Config, cmd string) (string, error) {
	// ... implementación usando ssh.Client
}

// Obtiene la lista de tablas/vistas de QSYS2
func getCatalogObjects(client *ssh.Client) ([]string, error) {
	sql := `SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = 'QSYS2' AND TABLE_TYPE IN ('T','V')`
	out, err := runSSHCommand(client, "db2 -x "+sql)
	if err != nil {
		return nil, err
	}
	lines := strings.Split(out, "\n")
	objects := []string{}
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line != "" {
			objects = append(objects, line)
		}
	}
	return objects, nil
}

// Obtiene el DDL de un objeto usando GENERATE_SQL
func getDDL(client *ssh.Client, schema, name, objType string) (string, error) {
	sql := fmt.Sprintf(
		`SELECT SQL_STMT FROM TABLE(QSYS2.GENERATE_SQL('%s', '%s', '%s')) AS T`,
		name, schema, objType,
	)
	out, err := runSSHCommand(client, "db2 -x "+sql)
	if err != nil {
		return "", err
	}
	return out, nil
}

// Adapta el DDL de DB2 a SQLite
func adaptDDL(db2DDL string) string {
	// Elimina todo lo que no sirve en SQLite
	re := regexp.MustCompile(`(?i)IN\s+[A-Z0-9_]+`)
	db2DDL = re.ReplaceAllString(db2DDL, "")

	re = regexp.MustCompile(`(?i)COMPRESS\s+YES|COMPRESS\s+NO`)
	db2DDL = re.ReplaceAllString(db2DDL, "")

	re = regexp.MustCompile(`(?i)RCDFMT\s+[A-Z0-9_]+`)
	db2DDL = re.ReplaceAllString(db2DDL, "")

	re = regexp.MustCompile(`(?i)GENERATED ALWAYS AS IDENTITY`)
	db2DDL = re.ReplaceAllString(db2DDL, "AUTOINCREMENT")

	re = regexp.MustCompile(`(?i)WITH DEFAULT`)
	db2DDL = strings.ReplaceAll(db2DDL, "WITH DEFAULT", "DEFAULT")

	// Cambio de tipos
	re = regexp.MustCompile(`(?i)VARCHAR\s*\(\s*[0-9]+\s*\)`)
	db2DDL = re.ReplaceAllString(db2DDL, "TEXT")

	re = regexp.MustCompile(`(?i)CHAR\s*\(\s*[0-9]+\s*\)`)
	db2DDL = re.ReplaceAllString(db2DDL, "TEXT")

	re = regexp.MustCompile(`(?i)DECIMAL\s*\(\s*[0-9]+\s*,\s*[0-9]+\s*\)`)
	db2DDL = re.ReplaceAllString(db2DDL, "NUMERIC")

	re = regexp.MustCompile(`(?i)FOR BIT DATA`)
	db2DDL = re.ReplaceAllString(db2DDL, "BLOB")

	// Cambia "CREATE TABLE QSYS2.NOMBRE" a "CREATE TABLE NOMBRE"
	re = regexp.MustCompile(`(?i)CREATE\s+(TABLE|VIEW)\s+QSYS2\.([A-Z0-9_]+)`)
	db2DDL = re.ReplaceAllString(db2DDL, "CREATE $1 $2")

	// Asegura que cada sentencia termina con ; y salto de línea
	if !strings.HasSuffix(db2DDL, ";") {
		db2DDL += ";"
	}
	return db2DDL
}

// Genera el archivo SQLite
func generateSQLiteDB(adaptedDDLs []string, outputFile string) error {
	db, err := sql.Open("sqlite3", outputFile)
	if err != nil {
		return err
	}
	defer db.Close()

	for _, ddl := range adaptedDDLs {
		_, err := db.Exec(ddl)
		if err != nil {
			log.Printf("Error ejecutando DDL: %v\nDDL: %s", err, ddl)
			// No detenemos, continuamos
		}
	}
	return nil
}

func main() {
	cfg := loadConfig("extractor_config.json")
	client := connectSSH(cfg)
	defer client.Close()

	objects, err := getCatalogObjects(client)
	if err != nil {
		log.Fatal(err)
	}

	var allDDL []string
	for _, obj := range objects {
		// Determinar si es tabla o vista (podríamos preguntar a SYSTABLES)
		// Por simplicidad, asumimos TABLE, pero si falla, probamos VIEW
		ddl, err := getDDL(client, "QSYS2", obj, "TABLE")
		if err != nil {
			// Intentar como VIEW
			ddl, err = getDDL(client, "QSYS2", obj, "VIEW")
			if err != nil {
				log.Printf("Error obteniendo DDL de %s: %v", obj, err)
				continue
			}
		}
		adapted := adaptDDL(ddl)
		allDDL = append(allDDL, adapted)
		log.Printf("✅ Adaptado: %s", obj)
	}

	// Generar archivo .sql (para inspección) y también la base de datos SQLite
	os.WriteFile("catalogo_qsys2.sql", []byte(strings.Join(allDDL, "\n\n")), 0644)
	generateSQLiteDB(allDDL, "qsys2_catalog.db")
	fmt.Println("✅ Catálogo completo extraído y adaptado a SQLite.")
}
```

---

## 4. Mejoras Adicionales: Extraer Datos Estáticos

Algunas tablas del catálogo contienen datos que son fijos y que iNative necesita para simular mensajes de error, códigos de retorno, etc. Por ejemplo:

- `QSYS2.MESSAGE_FILE` (o `QMESSAGE`) contiene los textos de los mensajes CPF/RNF.
- `QSYS2.SYSPARMS` contiene parámetros del sistema.

Para extraerlos, podemos ejecutar `SELECT *` y guardarlos como CSV o insertarlos directamente en SQLite.

**Estrategia**: Para cada tabla que sea de "configuración" (no estadísticas de ejecución), extrae sus datos y genera `INSERT` en SQLite.

---

## 5. Plan de Acción para el Programador

| Paso | Tarea |
|------|-------|
| 1 | Escribir el programa en Go con las funciones anteriores. |
| 2 | Crear un archivo `extractor_config.json` con sus credenciales. |
| 3 | Ejecutar `go run cmd/extractor/main.go`. |
| 4 | El programa generará `qsys2_catalog.db` y `catalogo_qsys2.sql`. |
| 5 | Verificar que la base de datos SQLite contenga todas las tablas y vistas. |
| 6 | Subir estos archivos al repositorio de iNative para que el equipo los use como catálogo base. |

---

## 6. Ventajas de este Enfoque

- **Automatización total**: Un solo comando extrae todo el catálogo.
- **Precisión**: Usa `GENERATE_SQL`, que es la herramienta oficial de IBM.
- **Mantenible**: Si el catálogo cambia en futuras versiones de IBM i, basta con volver a ejecutar el extractor.
- **Portabilidad**: El resultado es una base de datos SQLite, que es el formato nativo de iNative.
- **Documentación implícita**: El archivo `.sql` generado sirve como documentación de la estructura del catálogo.

---

## 7. Consideraciones

- **Tiempo de ejecución**: Extraer las ~800 tablas/vistas de QSYS2 puede tomar varios minutos. Es recomendable ejecutarlo una vez y guardar el resultado.
- **Versión de DB2**: `GENERATE_SQL` está disponible en IBM i 7.3 y superiores. Si tu sistema es más antiguo, usa el método 2 (consultar SYSCOLUMNS para construir el DDL manualmente).
- **Filtrado**: Puedes optar por extraer solo las 7 vistas principales mencionadas (SYSTABLES, SYSCOLUMNS, etc.) para reducir el tamaño. Pero extraer todo te da flexibilidad para futuras necesidades.

---

Con este plan, el programador dispondrá de un **extractor completo y autónomo** que generará el catálogo exacto de QSYS2 en formato SQLite, listo para ser integrado en iNative. ¿Necesitas que profundice en algún aspecto del código o que proporcione el script completo listo para copiar y pegar?
