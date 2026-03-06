package agent

import (
	"trpc.group/trpc-go/trpc-agent-go/agent/llmagent"
	"trpc.group/trpc-go/trpc-agent-go/model"
	"trpc.group/trpc-go/trpc-agent-go/model/openai"
	"trpc.group/trpc-go/trpc-agent-go/runner"
	"trpc.group/trpc-go/trpc-agent-go/session/inmemory"
	"trpc.group/trpc-go/trpc-agent-go/tool"
)

func NewRunner(cfg Config) runner.Runner {
	mdl := openai.New(cfg.ModelName,
		openai.WithAPIKey(cfg.APIKey),
		openai.WithBaseURL("https://api.anthropic.com/v1"),
		openai.WithVariant("anthropic"),
	)

	genConfig := model.GenerationConfig{
		Stream: true,
	}

	tools := []tool.Tool{
		NewCalcTool(),
		NewTimeTool(),
		NewLookTool(),
	}

	agent := llmagent.New("hugo",
		llmagent.WithModel(mdl),
		llmagent.WithTools(tools),
		llmagent.WithInstruction("You are HUGO..."),
		llmagent.WithGenerationConfig(genConfig),
	)

	r := runner.NewRunner("hugo", agent, runner.WithSessionService(inmemory.NewSessionService()))

	return r
}
