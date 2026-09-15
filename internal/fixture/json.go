package fixture

import (
	"encoding/json"
	"os"
)

// Load reads a fixture from its JSON representation.
func Load(data []byte) (Fixture, error) {
	var f Fixture
	err := json.Unmarshal(data, &f)
	return f, err
}

// LoadFile reads and parses a fixture from a path.
func LoadFile(path string) (Fixture, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Fixture{}, err
	}
	return Load(data)
}

// Marshal serializes a fixture to indented JSON.
func Marshal(f Fixture) ([]byte, error) {
	return json.MarshalIndent(f, "", "  ")
}
