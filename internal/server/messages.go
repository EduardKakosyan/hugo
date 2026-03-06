// Package server
package server

type ClientMessage struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

type ServerMessage struct {
	Type   string `json:"type"`
	Text   string `json:"text,omitempty"`
	Tool   string `json:"tool,omitempty"`   // for "tool_call", "tool_result"
	Args   string `json:"args,omitempty"`   // for "tool_call" — raw JSON string
	Result string `json:"result,omitempty"` // for "tool_result"
	Error  string `json:"error,omitempty"`
}
