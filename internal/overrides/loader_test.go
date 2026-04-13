package overrides

import (
	"math"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadOverridesRealFile(t *testing.T) {
	path := filepath.Clean(filepath.Join("..", "..", "location-override.json"))

	loaded, err := LoadOverrides(path)
	if err != nil {
		t.Fatalf("LoadOverrides(%q) returned error: %v", path, err)
	}

	if got, want := len(loaded), 12; got != want {
		t.Fatalf("override entry count mismatch: got %d want %d", got, want)
	}

	cases := []struct {
		name string
		key  string
		want [3]float64
	}{
		{
			name: "ne073 Penzance",
			key:  "021a29e755951b0f0267c0357e8d01489ae41abbe54818e4975b33ca5553b7a902",
			want: [3]float64{50.09916, -5.55674, 153.8},
		},
		{
			name: "ne004 Penzance",
			key:  "037ec65f987b30ee72e2f159d3d1cb1786f2368b35d4655d9beccd7803ab7e7c1f",
			want: [3]float64{50.12993, -5.5137, 56.3},
		},
	}

	for _, tc := range cases {
		got, ok := loaded[tc.key]
		if !ok {
			t.Fatalf("missing override for %s (%s)", tc.name, tc.key)
		}

		if !almostEqual(got[0], tc.want[0]) || !almostEqual(got[1], tc.want[1]) || !almostEqual(got[2], tc.want[2]) {
			t.Fatalf("%s mismatch: got %v want %v", tc.name, got, tc.want)
		}
	}
}

func TestLoadOverridesMissingFile(t *testing.T) {
	_, err := LoadOverrides(filepath.Join("..", "..", "does-not-exist-location-override.json"))
	if err == nil {
		t.Fatalf("expected missing file error, got nil")
	}
	if !strings.Contains(err.Error(), "missing") {
		t.Fatalf("expected missing file hint in error, got: %v", err)
	}
}

func almostEqual(a, b float64) bool {
	const epsilon = 1e-9
	return math.Abs(a-b) < epsilon
}
