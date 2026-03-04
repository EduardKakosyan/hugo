package agent

import (
	"fmt"
	"os"
)

type Config struct {
	ModelName string
	APIKEY    string
	MaxTokens int
}

// NewDefaultConfig returns a Config struct with the default values.
func NewDefaultConfig() Config {
	return Config{
		ModelName: "claude-sonnet-4-20250514",
		APIKEY:    "test-key",
		MaxTokens: 2000,
	}
}

func LoadConfig() (Config, error) {
	key := os.Getenv("ANTHROPIC_API_KEY")
	if key == "" {
		return Config{}, fmt.Errorf("ANTHROPIC_API_KEY is not set")
	}

	return Config{
		ModelName: "claude-sonnet-4-20250514",
		APIKEY:    key,
		MaxTokens: 2000,
	}, nil
}
