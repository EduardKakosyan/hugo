package voice

import (
	"fmt"
	"sync"

	sherpa "github.com/k2-fsa/sherpa-onnx-go/sherpa_onnx"
)

type TTS struct {
	engine *sherpa.OfflineTts
	mu     sync.Mutex // sherpa-onnx is not thread-safe for concurrent Generate calls
}

type TTSConfig struct {
	Model      string // path to model.onnx
	Voices     string // path to voices.bin
	Tokens     string // path to tokens.txt
	DataDir    string // path to espeak-ng-data/
	NumThreads int
	SpeakerID  int     // which voice to use ( 0 - 10 for kokor-en-v0_19)
	Speed      float32 // 1.0 normal , <1 = slower, >1 = faster
}

func NewTTS(cfg TTSConfig) (*TTS, error) {
	config := sherpa.OfflineTtsConfig{}
	config.Model.Kokoro.Model = cfg.Model
	config.Model.Kokoro.Voices = cfg.Voices
	config.Model.Kokoro.Tokens = cfg.Tokens
	config.Model.Kokoro.DataDir = cfg.DataDir
	config.Model.NumThreads = cfg.NumThreads
	config.Model.Provider = "cpu"
	config.MaxNumSentences = 1

	engine := sherpa.NewOfflineTts(&config)
	if engine == nil {
		return nil, fmt.Errorf("failed to create TTS engine - check model paths")
	}

	return &TTS{engine: engine}, nil
}

func (t *TTS) SampleRate() int {
	return t.engine.SampleRate()
}

// Synthesize converts text to float32 audio smaples.
// Returns the full audio after synthesis completes.
func (t *TTS) Synthesize(text string, speakerID int, speed float32) []float32 {
	t.mu.Lock()
	defer t.mu.Unlock()

	audio := t.engine.Generate(text, speakerID, speed)
	return audio.Samples
}

// SynthesizeWithCallback streams aduio chunks during syntheiss.
// The callback receives partial []float32 samples as they're generated
// Returns true from the callback to continue, false to abort.
func (t *TTS) SynthesizeWithCallback(
	text string, speakerID int, speed float32, cb func(samples []float32) bool,
) []float32 {
	t.mu.Lock()
	defer t.mu.Unlock()

	audio := t.engine.GenerateWithCallback(text, speakerID, speed, cb)
	return audio.Samples
}

// Close frees the underlying C resources.
func (t *TTS) Close() {
	sherpa.DeleteOfflineTts(t.engine)
}
