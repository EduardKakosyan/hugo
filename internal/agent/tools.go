package agent

import (
	"context"
	"time"

	"trpc.group/trpc-go/trpc-agent-go/tool/function"
)

type TimeInput struct{}

type TimeOutput struct {
	CurrentTime string `json:"current_time" jsonschema:"description=Current date and time"`
}

type CalcInput struct {
	Operation string  `json:"operation" jsonschema:"description=Math operation to perform, required, enum=add, enum=subtract, enum=multiply, enum=divide"`
	A         float64 `json:"a" jsonschema:"description=First number, required"`
	B         float64 `json:"b" jsonschema:"secription=Second number, required"`
}

type CalcOutput struct {
	Result float64 `json:"result" jsonschema:"descriptio=Calculation Result"`
	Error  string  `json:"error,omitempty" jsonschema:"description=Error message if operation failed"`
}

func getTime(_ context.Context, _ TimeInput) (TimeOutput, error) {
	return TimeOutput{
		CurrentTime: time.Now().Format(time.RFC1123),
	}, nil
}

func NewTimeTool() *function.FunctionTool[TimeInput, TimeOutput] {
	return function.NewFunctionTool(getTime, function.WithName("current_time"), function.WithDescription("Returns the current date and time"))
}

func calculate(_ context.Context, args CalcInput) (CalcOutput, error) {
	switch args.Operation {
	case "add":
		return CalcOutput{Result: args.A + args.B}, nil
	case "subtract":
		return CalcOutput{Result: args.A - args.B}, nil
	case "multiply":
		return CalcOutput{Result: args.A * args.B}, nil
	case "divide":
		if args.B == 0 {
			return CalcOutput{Error: "division by zero"}, nil
		}
		return CalcOutput{Result: args.A / args.B}, nil
	default:
		return CalcOutput{Error: "unknown operation: " + args.Operation}, nil
	}
}

func NewCalcTool() *function.FunctionTool[CalcInput, CalcOutput] {
	return function.NewFunctionTool(
		calculate,
		function.WithName("calculator"),
		function.WithDescription("Performs basic math: add, subtract, multiply, divide"),
	)
}
