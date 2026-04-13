package parser

import (
	"bytes"
	"encoding/binary"
	"math"
	"testing"
)

func TestParsePacketSynthetic(t *testing.T) {
	rawModeS := []byte{
		0x8d, 0x39, 0x86, 0x02, 0x58, 0x9b, 0x84,
		0xce, 0x73, 0x02, 0xe3, 0x5b, 0xbd, 0x70,
	}

	packet := buildPacket(
		870800659,
		50.00001,
		-5.50002,
		42.75,
		48332,
		506707868,
		rawModeS,
	)

	obs, err := ParsePacket(bytes.NewReader(packet), nil)
	if err != nil {
		t.Fatalf("ParsePacket returned error: %v", err)
	}

	if obs.SensorID != 870800659 {
		t.Fatalf("SensorID mismatch: got %d want %d", obs.SensorID, 870800659)
	}
	if !almostEqual(obs.Lat, 50.00001) || !almostEqual(obs.Lon, -5.50002) || !almostEqual(obs.AltM, 42.75) {
		t.Fatalf("coordinates mismatch: got lat/lon/alt %.6f %.6f %.2f", obs.Lat, obs.Lon, obs.AltM)
	}

	wantTotalNanos := int64(48332*1_000_000_000 + 506707868)
	if obs.TotalNanos != wantTotalNanos {
		t.Fatalf("TotalNanos mismatch: got %d want %d", obs.TotalNanos, wantTotalNanos)
	}

	wantHex := "8d398602589b84ce7302e35bbd70"
	if obs.Hex != wantHex {
		t.Fatalf("hex mismatch: got %q want %q", obs.Hex, wantHex)
	}
	if obs.HexKey != wantHex {
		t.Fatalf("hex key mismatch: got %q want %q", obs.HexKey, wantHex)
	}
	if obs.DF != 17 {
		t.Fatalf("DF mismatch: got %d want 17", obs.DF)
	}
}

func TestParsePacketAppliesNearestOverride(t *testing.T) {
	rawModeS := []byte{
		0x8d, 0x39, 0x86, 0x02, 0x58, 0x9b, 0x84,
		0xce, 0x73, 0x02, 0xe3, 0x5b, 0xbd, 0x70,
	}

	overrides := map[string][3]float64{
		"ne004": {50.12993, -5.5137, 56.3},
		"far":   {49.0, -8.0, 999.0},
	}

	// This masked location is within 0.1 deg of ne004.
	packet := buildPacket(
		870800659,
		50.09,
		-5.55,
		9999.0,
		100,
		250,
		rawModeS,
	)

	obs, err := ParsePacket(bytes.NewReader(packet), overrides)
	if err != nil {
		t.Fatalf("ParsePacket returned error: %v", err)
	}

	if !almostEqual(obs.Lat, 50.12993) || !almostEqual(obs.Lon, -5.5137) || !almostEqual(obs.AltM, 56.3) {
		t.Fatalf("override not applied correctly: got lat/lon/alt %.5f %.5f %.2f", obs.Lat, obs.Lon, obs.AltM)
	}
}

func buildPacket(sensorID int64, lat, lon, alt float64, secondsSinceMidnight, nanoseconds uint64, rawModeS []byte) []byte {
	payload := make([]byte, fixedHeaderSize+len(rawModeS))
	binary.BigEndian.PutUint64(payload[0:8], uint64(sensorID))
	binary.BigEndian.PutUint64(payload[8:16], math.Float64bits(lat))
	binary.BigEndian.PutUint64(payload[16:24], math.Float64bits(lon))
	binary.BigEndian.PutUint64(payload[24:32], math.Float64bits(alt))
	binary.BigEndian.PutUint64(payload[32:40], secondsSinceMidnight)
	binary.BigEndian.PutUint64(payload[40:48], nanoseconds)
	copy(payload[48:], rawModeS)

	packet := make([]byte, 1+len(payload))
	packet[0] = byte(len(payload))
	copy(packet[1:], payload)
	return packet
}

func almostEqual(a, b float64) bool {
	const epsilon = 1e-9
	return math.Abs(a-b) < epsilon
}
