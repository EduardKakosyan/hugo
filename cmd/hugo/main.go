package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"

	"hugo/internal/agent"

	"github.com/joho/godotenv"
	"trpc.group/trpc-go/trpc-agent-go/model"
)

func main() {
	_ = godotenv.Load(".env.local")

	cfg, err := agent.LoadConfig()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	r := agent.NewRunner(cfg)
	ctx := context.Background()
	scanner := bufio.NewScanner(os.Stdin)

	for {
		fmt.Print("You: ")

		if !scanner.Scan() {
			break
		}

		input := strings.TrimSpace(scanner.Text())

		if input == "" {
			continue
		}
		events, err := r.Run(
			ctx,
			"user-001",
			"session-001",
			model.NewUserMessage(input),
		)
		if err != nil {
			fmt.Print(err)
			continue
		}

		for event := range events {
			if event.Object == "chat.completion.chunk" {
				fmt.Print(event.Choices[0].Delta.Content)
			}
		}

		fmt.Println()
	}
}
