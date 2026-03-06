package server

import (
	"context"
	"fmt"
	"net/http"

	"github.com/gorilla/websocket"
	"trpc.group/trpc-go/trpc-agent-go/model"
	"trpc.group/trpc-go/trpc-agent-go/runner"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

// Server holds the HTTP server and the agent runner.
type Server struct {
	runner runner.Runner
	port   string
}

// New creates a new Server.
func New(r runner.Runner, port string) *Server {
	return &Server{
		runner: r,
		port:   port,
	}
}

func (s *Server) Start() error {
	mux := http.NewServeMux()

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "ok")
	})

	mux.HandleFunc("/ws", s.handleWS)
	fmt.Printf("Hugo server listening on :%s\n", s.port)
	return http.ListenAndServe(":"+s.port, mux)
}

func (s *Server) handleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}

	defer conn.Close()

	writeCh := make(chan ServerMessage, 16)

	go func() {
		for msg := range writeCh {
			if err := conn.WriteJSON(msg); err != nil {
				return
			}
		}
	}()

	for {
		var msg ClientMessage
		if err := conn.ReadJSON(&msg); err != nil {
			break
		}

		if msg.Type != "message" || msg.Text == "" {
			continue
		}

		s.processMessage(r.Context(), msg.Text, writeCh)
	}

	close(writeCh)
}

func (s *Server) processMessage(ctx context.Context, text string, writeCh chan<- ServerMessage) {
	events, err := s.runner.Run(
		ctx,
		"user-001",    // TODO: per-connection user ID
		"session-001", // TODO: per-connection session ID
		model.NewUserMessage(text),
	)
	if err != nil {
		writeCh <- ServerMessage{Type: "error", Error: err.Error()}
		return
	}

	for event := range events {
		if len(event.Choices) == 0 {
			continue
		}

		choice := event.Choices[0]

		if choice.Delta.Content != "" {
			writeCh <- ServerMessage{
				Type: "chunk",
				Text: choice.Delta.Content,
			}
		}

		// Tool call
		if len(choice.Message.ToolCalls) > 0 {
			for _, tc := range choice.Message.ToolCalls {
				writeCh <- ServerMessage{
					Type: "tool_call",
					Tool: tc.Function.Name,
					Args: string(tc.Function.Arguments),
				}
			}
		}

		// Tool result
		if choice.Message.Role == "tool" {
			writeCh <- ServerMessage{
				Type:   "tool_result",
				Tool:   choice.Message.ToolName,
				Result: choice.Message.Content,
			}
		}
	}

	// Signal that the response is complete
	writeCh <- ServerMessage{Type: "done"}
}
