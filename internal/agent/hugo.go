package agent

import (
	"trpc.group/trpc-go/trpc-agent-go/agent/llmagent"
	"trpc.group/trpc-go/trpc-agent-go/model"
	"trpc.group/trpc-go/trpc-agent-go/model/openai"
	"trpc.group/trpc-go/trpc-agent-go/runner"
	"trpc.group/trpc-go/trpc-agent-go/session/inmemory"
)

func CreateAgent(cfg Config) runner.Runner {
	mdl := openai.New(cfg.ModelName,
		openai.WithAPIKey(cfg.APIKEY),
		openai.WithBaseURL("https://api.anthropic.com/v1"),
		openai.WithVariant("anthropic"),
	)

	genConfig := model.GenerationConfig{
		Stream: true,
	}

	agent := llmagent.New("hugo",
		llmagent.WithModel(mdl),
		llmagent.WithInstruction("You are HUGO..."),
		llmagent.WithGenerationConfig(genConfig),
	)

	r := runner.NewRunner("hugo", agent, runner.WithSessionService(inmemory.NewSessionService()))

	return r
}
