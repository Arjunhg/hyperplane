package overrides

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
)

type overrideRecord struct {
	PublicKey string  `json:"public_key"`
	Lat       float64 `json:"lat"`
	Lon       float64 `json:"lon"`
	Alt       float64 `json:"alt"`
}

// LoadOverrides reads location-override.json and returns a lookup of
// public_key -> [lat, lon, alt].
func LoadOverrides(path string) (map[string][3]float64, error) {
	if path == "" {
		return nil, fmt.Errorf("location override path is empty")
	}

	content, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, fmt.Errorf("location override file missing at %q", path)
		}
		return nil, fmt.Errorf("read location override file %q: %w", path, err)
	}

	var records []overrideRecord
	if err := json.Unmarshal(content, &records); err != nil {
		return nil, fmt.Errorf("parse location override file %q: %w", path, err)
	}

	overrides := make(map[string][3]float64, len(records))
	for _, record := range records {
		if record.PublicKey == "" {
			continue
		}
		overrides[record.PublicKey] = [3]float64{record.Lat, record.Lon, record.Alt}
	}

	return overrides, nil
}
