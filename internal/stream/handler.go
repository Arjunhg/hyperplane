package stream

import (
	"errors"
	"io"
	"log"
	"net"
	"strings"

	"github.com/libp2p/go-libp2p/core/network"

	"quickstart/internal/parser"
	"quickstart/internal/publisher"
)

// HandleStream reads observations from one libp2p stream and publishes each
// parsed observation before reading the next packet.
func HandleStream(stream network.Stream, packetParser *parser.PacketParser, publisher *publisher.KafkaPublisher) {
	defer stream.Close()

	if packetParser == nil {
		log.Printf("stream handler misconfigured: parser is nil")
		return
	}
	if publisher == nil {
		log.Printf("stream handler misconfigured: publisher is nil")
		return
	}

	peerID := "<unknown>"
	if conn := stream.Conn(); conn != nil {
		peerID = conn.RemotePeer().String()
	}

	log.Printf("stream connected peer=%s", peerID)

	for {
		obs, err := packetParser.ParsePacket(stream)
		if err != nil {
			if isDisconnectError(err) {
				log.Printf("stream disconnected peer=%s: %v", peerID, err)
				return
			}

			log.Printf("stream parse error peer=%s: %v", peerID, err)
			continue
		}

		if err := publisher.Publish(obs); err != nil {
			log.Printf("stream publish error peer=%s sensor_id=%d hex=%s: %v", peerID, obs.SensorID, obs.Hex, err)
			continue
		}

		log.Printf(
			"observation peer=%s sensor_id=%d lat=%.5f lon=%.5f alt_m=%.1f total_nanos=%d hex=%s",
			peerID, obs.SensorID, obs.Lat, obs.Lon, obs.AltM, obs.TotalNanos, obs.Hex,
		)
	}
}

func isDisconnectError(err error) bool {
	if errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF) || errors.Is(err, net.ErrClosed) {
		return true
	}

	lower := strings.ToLower(err.Error())
	return strings.Contains(lower, "stream reset") || strings.Contains(lower, "connection reset")
}
