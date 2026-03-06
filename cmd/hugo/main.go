package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"

	"hugo/internal/agent"
	"hugo/internal/server"

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
	if len(os.Args) > 1 && os.Args[1] == "serve" {
		port := "8080"

		if len(os.Args) > 2 {
			port = os.Args[2]
		}

		srv := server.New(r, port)

		if err := srv.Start(); err != nil {
			fmt.Fprintf(os.Stderr, "Server error: %v\n", err)
			os.Exit(1)
		}
		return
	}

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
			if len(event.Choices) == 0 {
				continue
			}

			choice := event.Choices[0]

			if choice.Delta.Content != "" {
				fmt.Print(choice.Delta.Content)
			}

			if len(choice.Message.ToolCalls) > 0 {
				for _, tc := range choice.Message.ToolCalls {
					fmt.Printf("\n [tool] %s(%s)\n", tc.Function.Name, tc.Function.Arguments)
				}
			}

			if choice.Message.Role == "tool" {
				fmt.Printf("  [result] %s\n", choice.Message.Content)
			}
		}

		fmt.Println()
	}
}
