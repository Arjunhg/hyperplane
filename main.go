package main

import (
	"context"
	"log"
	"os"
	"strings"

	neuronsdk "github.com/NeuronInnovations/neuron-go-hedera-sdk"
	commonlib "github.com/NeuronInnovations/neuron-go-hedera-sdk/common-lib"
	"github.com/hashgraph/hedera-sdk-go/v2"
	"github.com/libp2p/go-libp2p/core/host"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/protocol"

	"quickstart/internal/overrides"
	"quickstart/internal/parser"
	"quickstart/internal/publisher"
	streamhandler "quickstart/internal/stream"
)

const (
	appVersion         = "0.1"
	defaultOverride    = "location-override.json"
	defaultKafkaTopic  = "modes-observations"
	defaultPublishMode = "kafka"
)

func main() {
	protocolID := protocol.ID("neuron/ADSB/0.0.2")

	overridePath := envOrDefault("LOCATION_OVERRIDE_FILE", defaultOverride)
	overrideMap, err := overrides.LoadOverrides(overridePath)
	if err != nil {
		log.Fatalf("failed to load location overrides: %v", err)
	}

	packetParser := parser.NewPacketParser(overrideMap)

	obsPublisher, err := buildPublisher()
	if err != nil {
		log.Fatalf("failed to create publisher: %v", err)
	}
	defer func() {
		if closeErr := obsPublisher.Close(); closeErr != nil {
			log.Printf("publisher close error: %v", closeErr)
		}
	}()

	log.Printf("loaded %d location override entries from %s", len(overrideMap), overridePath)

	neuronsdk.LaunchSDK(
		appVersion,
		protocolID,
		nil,
		func(ctx context.Context, h host.Host, b *commonlib.NodeBuffers) {
			h.SetStreamHandler(protocolID, func(streamConn network.Stream) {
				peerID := streamConn.Conn().RemotePeer()
				b.SetStreamHandler(peerID, &streamConn)
				streamhandler.HandleStream(streamConn, packetParser, obsPublisher)
			})
		},
		func(msg hedera.TopicMessage) {
			log.Printf("buyer topic message: %v", msg)
		},
		func(ctx context.Context, h host.Host, b *commonlib.NodeBuffers) {},
		func(msg hedera.TopicMessage) {
			log.Printf("seller topic message: %v", msg)
		},
	)
}

func buildPublisher() (*publisher.KafkaPublisher, error) {
	publishMode := strings.ToLower(envOrDefault("PUBLISH_MODE", defaultPublishMode))
	kafkaTopic := envOrDefault("KAFKA_TOPIC", defaultKafkaTopic)
	kafkaBrokers := parseBrokers(os.Getenv("KAFKA_BROKERS"))

	if publishMode == "stdout" || len(kafkaBrokers) == 0 {
		log.Printf("using stdout publisher (topic=%s)", kafkaTopic)
		return publisher.NewStdoutPublisher(os.Stdout), nil
	}

	kafkaPublisher, err := publisher.NewKafkaPublisher(kafkaBrokers, kafkaTopic)
	if err != nil {
		log.Printf("kafka unavailable, falling back to stdout publisher: %v", err)
		return publisher.NewStdoutPublisher(os.Stdout), nil
	}

	log.Printf("using kafka publisher (brokers=%v topic=%s)", kafkaBrokers, kafkaTopic)
	return kafkaPublisher, nil
}

func envOrDefault(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func parseBrokers(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}

	parts := strings.Split(raw, ",")
	brokers := make([]string, 0, len(parts))
	for _, part := range parts {
		broker := strings.TrimSpace(part)
		if broker != "" {
			brokers = append(brokers, broker)
		}
	}

	return brokers
}
