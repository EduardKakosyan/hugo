package voice

import "context"

// Pipeline orchestrates the full voice loop:
// - Input: Mic -> Vac -> Stt -> transcript channel
// - Output: speech queue -> TTS -> speaker

type Pipeline interface {
	// Start begins listening. Transcripts arrive on the returned channel.
	Start(ctx context.Context) (<-chan Transcript, error)

	// Enqueue adds text to the speech queeue. Non-blocking.
	Enqueue(ctx context.Context, text string) error

	// DrainQueue discards queued speech that hasn't started playing.
	DrainQueue()

	// Interrupt stops current TTS audio AND drains the queue.
	Interrupt()

	// IsSpeaking returns trueif auto is playing or the queue has items.
	IsSpeaking() bool

	// Close shuts down all goroutines.
	Close() error
}
