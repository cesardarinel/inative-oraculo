package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	_ "modernc.org/sqlite"
)

type Observable struct {
	Kind  string `json:"kind"`
	Name  string `json:"name"`
	Value interface{} `json:"value"`
}

type Snapshot struct {
	Observables []Observable `json:"observables"`
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("uso: load_oracle_seed.go <snapshot.json>")
		return
	}
	data, err := os.ReadFile(os.Args[1])
	if err != nil { panic(err) }
	var s Snapshot
	if err := json.Unmarshal(data, &s); err != nil { panic(err) }

	db, err := sql.Open("sqlite", "file:dev.db?_foreign_keys=on")
	if err != nil { panic(err) }
	defer db.Close()

	// Crear tabla objects si no existe
	_, _ = db.Exec(`CREATE TABLE IF NOT EXISTS objects (
		lib TEXT, name TEXT, type TEXT, attribute TEXT, objtext TEXT,
		objsize INTEGER, created_at TEXT, changed_at TEXT, owner TEXT, definer TEXT, iasp TEXT
	)`)
	// Limpiar y cargar objetos
	_, _ = db.Exec(`DELETE FROM objects`)
	for _, o := range s.Observables {
		if o.Kind != "objects" { continue }
		arr, ok := o.Value.([]interface{})
		if !ok { continue }
		for _, v := range arr {
			s := fmt.Sprint(v)
			parts := strings.Split(s, " ")
			if len(parts) < 3 { continue }
			lib := parts[0]
			name := parts[1]
			typ := parts[2]
			_, _ = db.Exec(`INSERT INTO objects(lib,name,type,attribute,objtext,objsize,created_at,changed_at,owner,definer,iasp) VALUES(?,?,?,?,?,?,?,?,?,?,?)`,
				lib, name, typ, "", "", 8192, "2024-01-01", "2024-01-01", "DEVUSER", "DEVUSER", "*SYSBAS")
		}
	}
	fmt.Println("seed loaded")
}
