package main

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"hugo/internal/agent"

	"github.com/joho/godotenv"
)

func main() {
	_ = godotenv.Load()

	cfg, err := agent.LoadConfig()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

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

		fmt.Println(input)
		fmt.Println(cfg.APIKEY)
	}
}
