package parser

import (
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"io"
	"math"
)

const (
	fixedHeaderSize = 48
	maxOverrideDist = 0.1
)

// Observation is the normalized payload sent to Redpanda/Python.
type Observation struct {
	SensorID   int64   `json:"sensor_id"`
	SensorPK   string  `json:"sensor_pk"`
	Lat        float64 `json:"lat"`
	Lon        float64 `json:"lon"`
	AltM       float64 `json:"alt_m"`
	TotalNanos int64   `json:"total_nanos"`
	Hex        string  `json:"hex"`
	DF         int     `json:"df"`
	HexKey     string  `json:"hex_key"`
}

type PacketParser struct {
	overrides map[string][3]float64
}

func NewPacketParser(overrides map[string][3]float64) *PacketParser { // * => This is just a promise: "I will return an address to a PacketParser."
	return &PacketParser{overrides: overrides}
}

func (p *PacketParser) ParsePacket(r io.Reader) (*Observation, error) {
	return ParsePacket(r, p.overrides)
}

// ParsePacket reads one 4DSky packet from r.
func ParsePacket(r io.Reader, overrides map[string][3]float64) (*Observation, error) {
	lengthPrefix := make([]byte, 1)
	if _, err := io.ReadFull(r, lengthPrefix); err != nil {
		return nil, err
	}

	packetLength := int(lengthPrefix[0])
	packet := make([]byte, packetLength)
	if _, err := io.ReadFull(r, packet); err != nil {
		return nil, err
	}
	if packetLength < fixedHeaderSize+1 {
		return nil, fmt.Errorf("invalid packet length %d: smaller than header+payload", packetLength)
	}

	sensorID := int64(binary.BigEndian.Uint64(packet[0:8]))
	lat := math.Float64frombits(binary.BigEndian.Uint64(packet[8:16]))
	lon := math.Float64frombits(binary.BigEndian.Uint64(packet[16:24]))
	alt := math.Float64frombits(binary.BigEndian.Uint64(packet[24:32]))
	secondsSinceMidnight := binary.BigEndian.Uint64(packet[32:40])
	nanoseconds := binary.BigEndian.Uint64(packet[40:48])
	rawModeS := packet[48:]

	if len(rawModeS) == 0 {
		return nil, fmt.Errorf("invalid packet: raw Mode-S payload is empty")
	}

	lat, lon, alt = applyNearestOverride(lat, lon, alt, overrides)

	totalNanos := int64(secondsSinceMidnight*1_000_000_000 + nanoseconds)
	hexPayload := hex.EncodeToString(rawModeS)
	df := int((rawModeS[0] >> 3) & 0x1F)

	return &Observation{
		SensorID:   sensorID,
		Lat:        lat,
		Lon:        lon,
		AltM:       alt,
		TotalNanos: totalNanos,
		Hex:        hexPayload,
		DF:         df,
		HexKey:     hexPayload,
	}, nil
}

func applyNearestOverride(lat, lon, alt float64, overrides map[string][3]float64) (float64, float64, float64) {
	if len(overrides) == 0 {
		return lat, lon, alt
	}

	bestDistance := math.MaxFloat64
	bestCoords := [3]float64{}
	found := false

	for _, coords := range overrides {
		dLat := lat - coords[0]
		dLon := lon - coords[1]
		distance := math.Hypot(dLat, dLon)

		if distance <= maxOverrideDist && distance < bestDistance {
			bestDistance = distance
			bestCoords = coords
			found = true
		}
	}

	if !found {
		return lat, lon, alt
	}

	return bestCoords[0], bestCoords[1], bestCoords[2]
}
