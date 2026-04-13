package publisher

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sync"
	"time"

	"github.com/segmentio/kafka-go"

	"quickstart/internal/parser"
)

type KafkaPublisher struct {
	topic  string
	writer *kafka.Writer
	stdout io.Writer
	mu     sync.Mutex
}

func NewKafkaPublisher(brokers []string, topic string) (*KafkaPublisher, error) {
	if len(brokers) == 0 {
		return nil, fmt.Errorf("kafka brokers list is empty")
	}
	if topic == "" {
		return nil, fmt.Errorf("kafka topic is empty")
	}

	conn, err := kafka.Dial("tcp", brokers[0])
	if err != nil {
		return nil, fmt.Errorf("connect to kafka broker %q: %w", brokers[0], err)
	}
	_ = conn.Close()

	writer := &kafka.Writer{
		Addr:         kafka.TCP(brokers...),
		Topic:        topic,
		Balancer:     &kafka.Hash{},
		RequiredAcks: kafka.RequireOne,
		BatchTimeout: 10 * time.Millisecond,
	}

	return &KafkaPublisher{
		topic:  topic,
		writer: writer,
	}, nil
}

// NewStdoutPublisher is used in local development when Redpanda is not available.
func NewStdoutPublisher(out io.Writer) *KafkaPublisher {
	if out == nil {
		out = os.Stdout
	}
	return &KafkaPublisher{
		topic:  "stdout",
		stdout: out,
	}
}

func (p *KafkaPublisher) Publish(obs *parser.Observation) error {
	if p == nil {
		return fmt.Errorf("publisher is nil")
	}
	if obs == nil {
		return fmt.Errorf("observation is nil")
	}

	payload, err := json.Marshal(obs)
	if err != nil {
		return fmt.Errorf("marshal observation: %w", err)
	}

	if p.stdout != nil {
		p.mu.Lock()
		defer p.mu.Unlock()

		if _, err := fmt.Fprintln(p.stdout, string(payload)); err != nil {
			return fmt.Errorf("write observation to stdout: %w", err)
		}
		return nil
	}

	if p.writer == nil {
		return fmt.Errorf("kafka writer is not initialized")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := p.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(obs.HexKey),
		Value: payload,
		Time:  time.Now().UTC(),
	}); err != nil {
		return fmt.Errorf("publish to kafka topic %q: %w", p.topic, err)
	}

	return nil
}

func (p *KafkaPublisher) Close() error {
	if p == nil || p.writer == nil {
		return nil
	}
	if err := p.writer.Close(); err != nil {
		return fmt.Errorf("close kafka writer: %w", err)
	}
	return nil
}
