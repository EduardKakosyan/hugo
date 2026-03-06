# Learning Go Through HUGO — Step-by-Step Guide

This guide walks you through Go from zero while building HUGO.
Each step introduces one concept, explains it, then asks you to write code.
Do not copy-paste — type every line yourself.

**Book companion:** "Learning Go: An Idiomatic Approach" by Jon Bodner.
Chapter references are included at each step.

---

## Step 0: Hello World

**Goal:** Understand packages, imports, `func main()`, and `go run`.

**Concepts:**
- Every `.go` file starts with `package <name>`
- `package main` is special — it tells Go "this is an executable program"
- `func main()` is the entry point — Go calls this when you run the program
- `fmt` is the standard library package for formatted I/O (printing, formatting)
- `import` brings in packages you want to use

**Book:** Chapter 1 (Setting Up Your Go Environment), Chapter 2 (Primitive Types — just the Println parts)

**Task:** Create the file `cmd/hugo/main.go` and write a program that prints `HUGO starting up`.

**What you need:**
```
package main       ← declares this file as part of the main (executable) package

import "fmt"       ← imports the fmt package from the standard library

func main() {      ← entry point — Go runs this function first
    // your Println call here
}
```

**Run it:**
```bash
mkdir -p cmd/hugo
# write your file
go run ./cmd/hugo
```

**Why `./cmd/hugo` and not `cmd/hugo/main.go`?**
`go run ./cmd/hugo` tells Go "build and run the package in this directory."
Go finds all `.go` files in that directory with `package main` and compiles them
together. This matters later when you have multiple files in the same package.

**Checkpoint:** You should see `HUGO starting up` printed. If you get an error,
read it carefully — Go error messages are specific and tell you the exact line.

---

## Step 1: Initialize the Module

**Goal:** Understand Go modules — how Go manages your project and its dependencies.

**Concepts:**
- A **module** is a collection of Go packages with a `go.mod` file at the root
- `go.mod` declares: your module's name (import path), Go version, and dependencies
- The module name is conventionally a URL path (like `github.com/eduardkakosyan/hugo`)
  even if the repo doesn't exist yet — it's just a unique identifier
- `go.sum` is auto-generated — it locks exact dependency versions (like a lockfile)

**Book:** Chapter 10 (Modules, Packages, and Imports)

**Task:** From the repo root, run:
```bash
go mod init github.com/eduardkakosyan/hugo
```

Then open `go.mod` and read it. It should have two lines:
```
module github.com/eduardkakosyan/hugo
go 1.26
```

Now run your program again:
```bash
go run ./cmd/hugo
```

It still works — but now Go knows this is a proper module.

**Why this matters:** When you later `import "github.com/eduardkakosyan/hugo/internal/agent"`,
Go resolves that relative to your module name in `go.mod`. Without a module, Go
can't resolve internal imports.

---

## Step 2: Variables, Types, and Structs

**Goal:** Learn how Go declares variables and defines custom types.

**Concepts:**
- Go is **statically typed** — every variable has a fixed type at compile time
- `:=` is **short variable declaration** — Go infers the type from the right side
- `var` is **explicit declaration** — you specify the type
- A **struct** groups related data into a single type (like a class without methods, for now)
- Struct fields are **capitalized = exported** (visible outside the package),
  **lowercase = unexported** (private to the package)

**Book:** Chapter 2 (Primitive Types and Declarations), Chapter 7 (Types, Methods, Interfaces — just the struct parts)

**Task:** In `cmd/hugo/main.go`, replace your hello world with:

1. Define a struct called `Config` with these fields:
   - `ModelName` (string) — the LLM model to use
   - `APIKey` (string) — the API key
   - `MaxTokens` (int) — max response tokens

2. In `main()`:
   - Create a `Config` value using a **struct literal** (the `TypeName{field: value}` syntax)
   - Print each field using `fmt.Printf`

**Syntax reference:**
```go
// Struct definition
type Config struct {
    ModelName string
    APIKey    string
    MaxTokens int
}

// Struct literal (creating a value)
cfg := Config{
    ModelName: "claude-sonnet-4-20250514",
    APIKey:    "test-key",
    MaxTokens: 2000,
}

// Printf formatting
// %s = string, %d = integer, %v = any value (Go picks the format)
// \n = newline
fmt.Printf("Model: %s\n", cfg.ModelName)
```

**Checkpoint:** Running `go run ./cmd/hugo` prints the three config fields.

**Experiment:** Try accessing `cfg.modelName` (lowercase m). What error do you get?
This is Go's visibility rule — but within the same package, you can still access
lowercase fields. The rule only matters across package boundaries. We'll see this
in Step 3.

---

## Step 3: Multiple Files and Packages

**Goal:** Split code into separate packages — the foundation of Go project structure.

**Concepts:**
- All `.go` files in the same directory must have the same `package` declaration
- You can have multiple `.go` files in one package — they can see each other's
  types, functions, and variables freely (no imports needed within a package)
- The `internal/` directory is special in Go: packages under it can only be
  imported by code within the same module. It's Go's built-in encapsulation.
- To use a type from another package, you **import** the package and prefix with
  the package name: `agent.Config`

**Book:** Chapter 10 (Modules, Packages, and Imports)

**Task:**

**File 1: `internal/agent/config.go`**
- Package declaration: `package agent`
- Move your `Config` struct here
- Add a function `NewDefaultConfig()` that returns a `Config` with sensible defaults

**File 2: `cmd/hugo/main.go`**
- Import your agent package: `"github.com/eduardkakosyan/hugo/internal/agent"`
- Call `agent.NewDefaultConfig()` and print the result

**Syntax reference:**
```go
// internal/agent/config.go
package agent

// NewDefaultConfig returns a Config with default values.
// Functions that create a value are conventionally named New<Type> in Go.
func NewDefaultConfig() Config {
    return Config{
        // fill in defaults
    }
}
```

```go
// cmd/hugo/main.go
package main

import (
    "fmt"
    "github.com/eduardkakosyan/hugo/internal/agent"
)

func main() {
    cfg := agent.NewDefaultConfig()
    fmt.Printf("Config: %+v\n", cfg)
    // %+v prints struct field names AND values
}
```

**Checkpoint:** `go run ./cmd/hugo` prints the config from the agent package.

**Key insight:** `main.go` doesn't know HOW Config is built — it just calls
`NewDefaultConfig()`. This is a factory function pattern, very common in Go.

---

## Step 4: Error Handling

**Goal:** Learn Go's explicit error handling — the most distinctive Go pattern.

**Concepts:**
- Go has **no exceptions**. Functions that can fail return an `error` as the last value.
- `error` is a built-in interface. If it's `nil`, everything is fine. If not, something failed.
- The pattern `if err != nil { ... }` is how you handle errors. You will write this hundreds of times.
- `fmt.Errorf("message: %w", err)` wraps an error with context
- **Never ignore errors.** If a function returns `(value, error)`, always check the error.

**Book:** Chapter 9 (Errors)

**Task:** Modify `internal/agent/config.go`:

1. Add a function `LoadConfig()` that returns `(Config, error)`
2. It should read the API key from an environment variable using `os.Getenv("ANTHROPIC_API_KEY")`
3. If the key is empty, return an error: `fmt.Errorf("ANTHROPIC_API_KEY is not set")`
4. If the key exists, return a Config with that key

Then update `cmd/hugo/main.go`:
1. Call `agent.LoadConfig()`
2. Check the error. If it's not nil, print the error and exit using `os.Exit(1)`
3. If no error, print the config (but mask the API key — don't print secrets)

**Syntax reference:**
```go
// Returning an error
func LoadConfig() (Config, error) {
    key := os.Getenv("ANTHROPIC_API_KEY")
    if key == "" {
        return Config{}, fmt.Errorf("ANTHROPIC_API_KEY is not set")
    }
    return Config{
        APIKey: key,
        // ... other fields
    }, nil    // nil means "no error"
}
```

```go
// Handling an error
cfg, err := agent.LoadConfig()
if err != nil {
    fmt.Fprintf(os.Stderr, "Error: %v\n", err)
    os.Exit(1)
}
```

**Imports you'll need:** `"os"` for `os.Getenv` and `os.Exit`, `"fmt"` for `fmt.Errorf`.

**Test it two ways:**
```bash
# Without the env var — should print error and exit
go run ./cmd/hugo

# With the env var — should print config
ANTHROPIC_API_KEY=test-key go run ./cmd/hugo
```

**Checkpoint:** Program exits with an error when the key is missing, runs normally when set.

---

## Step 5: Interfaces

**Goal:** Understand Go interfaces — the most powerful concept in Go.

**Concepts:**
- An **interface** is a set of method signatures. Any type that has those methods
  automatically satisfies the interface — no `implements` keyword needed.
- This is called **implicit satisfaction** or "structural typing"
- Interfaces are typically small — often just 1-2 methods
- Convention: interfaces are defined **where they're consumed**, not where they're implemented
- The `io.Reader` and `io.Writer` interfaces are the most famous — one method each

**Book:** Chapter 7 (Types, Methods, and Interfaces)

**Task:** We're going to define a `Greeter` interface to understand the concept,
then throw it away. This is purely for learning.

**File: `internal/agent/greeter.go`** (temporary, for learning)

1. Define an interface `Greeter` with one method: `Greet(name string) string`
2. Define a struct `FormalGreeter` with no fields
3. Add a method on `FormalGreeter` that returns `"Good day, <name>."`
4. Define a struct `CasualGreeter` with no fields
5. Add a method on `CasualGreeter` that returns `"Hey <name>!"`

**In `cmd/hugo/main.go`:**
1. Write a function `printGreeting(g agent.Greeter, name string)` that calls `g.Greet(name)` and prints it
2. Call it twice — once with `FormalGreeter{}`, once with `CasualGreeter{}`

**Syntax reference:**
```go
// Interface definition
type Greeter interface {
    Greet(name string) string
}

// Struct that satisfies it (no "implements" keyword)
type FormalGreeter struct{}

// Method on FormalGreeter — this is what makes it satisfy Greeter
func (f FormalGreeter) Greet(name string) string {
    return fmt.Sprintf("Good day, %s.", name)
}

// Using the interface — accepts ANY type with a Greet method
func printGreeting(g Greeter, name string) {
    fmt.Println(g.Greet(name))
}
```

**The `func (f FormalGreeter)` part is called a "receiver."**
It means "this function belongs to FormalGreeter." It's how Go does methods.
- `f` is the receiver variable (like `self` or `this` in other languages)
- `FormalGreeter` is the receiver type

**Checkpoint:** Two different greetings printed by the same function.

**Why this matters for HUGO:** The voice `Pipeline` interface, the `robot.Client`
interface, the `vision.Analyzer` interface — they all use this pattern. You write
the interface, then you can swap implementations (real Silero VAD vs. mock VAD)
without changing any code that uses the interface.

**Cleanup:** Delete `internal/agent/greeter.go` when you're done. It was just for practice.

---

## Step 6: Reading User Input (the Chat Loop)

**Goal:** Build an interactive stdin loop — this becomes the CLI chat interface.

**Concepts:**
- `bufio.Scanner` reads input line by line from any `io.Reader`
- `os.Stdin` is the standard input (your terminal)
- A `for` loop with no condition is Go's `while true` — it loops forever
- `break` exits the loop, `continue` skips to the next iteration
- `strings.TrimSpace` removes leading/trailing whitespace

**Book:** Chapter 4 (Blocks, Shadows, and Control Structures — for loops),
Chapter 13 (The Standard Library — io section)

**Task:** Update `cmd/hugo/main.go`:

1. After loading config, enter a loop that:
   - Prints `You: ` as a prompt (use `fmt.Print`, not `Println` — no newline)
   - Reads a line from stdin
   - If the line is `"exit"` or `"quit"`, break the loop
   - Otherwise print `HUGO: You said "<input>"` (echo it back for now)
2. After the loop, print `"Goodbye!"`

**Syntax reference:**
```go
scanner := bufio.NewScanner(os.Stdin)

for {
    fmt.Print("You: ")

    if !scanner.Scan() {
        break    // EOF or error — user pressed Ctrl+D
    }

    input := strings.TrimSpace(scanner.Text())

    if input == "" {
        continue    // skip empty lines
    }

    // your exit check and echo here
}
```

**Imports:** `"bufio"`, `"os"`, `"strings"`

**Checkpoint:** You can type messages, see them echoed back, and exit cleanly
with "quit" or Ctrl+D.

**This is the skeleton of Phase 1.** In Step 7, we replace the echo with
a real LLM agent call.

---

## Step 7: Adding a Third-Party Dependency

**Goal:** Learn how `go get` works and use a real external package.

**Concepts:**
- `go get <package>` downloads a package and adds it to `go.mod`
- Go modules use **Semantic Import Versioning** — the import path includes
  the major version for v2+ (`/v2`)
- `go mod tidy` cleans up: adds missing deps, removes unused ones
- Your `go.sum` file is the lockfile — commit it to git

**Book:** Chapter 10 (Modules, Packages, and Imports — the dependency sections)

**Task:** Add the `godotenv` package so we can load `.env` files:

```bash
go get github.com/joho/godotenv
```

Then update `cmd/hugo/main.go`:

1. At the very start of `main()`, before loading config, call `godotenv.Load()`
2. This loads variables from a `.env` file in the current directory into the environment
3. It returns an error — but a missing `.env` file is OK in production, so you can ignore it
4. Create a `.env` file at the repo root with: `ANTHROPIC_API_KEY=test-key-for-dev`

**Syntax reference:**
```go
import "github.com/joho/godotenv"

func main() {
    // _ means "I know this returns a value but I'm intentionally ignoring it"
    // This is the ONLY time you should ignore an error — when the docs say
    // "it's OK if this fails" (missing .env is fine)
    _ = godotenv.Load()

    cfg, err := agent.LoadConfig()
    // ...
}
```

**After adding it, look at your `go.mod`:**
```bash
cat go.mod
```

You'll see the dependency listed with its version. Also check `go.sum` exists now.

**Checkpoint:** Program loads the API key from `.env` instead of requiring you
to set it in the shell each time.

**Make sure `.env` is in `.gitignore`** — it already should be from the existing
gitignore patterns.

---

## Step 8: Your First tRPC-agent-go Agent

**Goal:** Wire up a real LLM agent and have a conversation.

**This is the payoff.** Everything you learned in Steps 0-7 comes together here.

**Concepts this step uses:**
- Packages and imports (Step 0, 1, 3)
- Structs (Step 2)
- Error handling (Step 4)
- Interfaces — the agent framework is interface-heavy (Step 5)
- The chat loop (Step 6)
- Third-party deps (Step 7)

### 8a: Get the dependency

```bash
go get trpc.group/trpc-go/trpc-agent-go
```

This may take a moment — it's a large framework with many sub-packages.
Run `go mod tidy` afterward to clean up.

### 8b: Create the agent definition

**File: `internal/agent/hugo.go`**

This file defines the HUGO agent. You need to:

1. Import the required sub-packages (I'll give you the import paths below)
2. Write a function `NewAgent(cfg Config) (agent, runner, error)` that:
   - Creates a model (using the anthropic provider)
   - Creates an LLMAgent with a system instruction
   - Creates a Runner with an inmemory session service
   - Returns the agent and runner

**Import paths you'll need:**
```go
import (
    "trpc.group/trpc-go/trpc-agent-go/agent/llmagent"
    "trpc.group/trpc-go/trpc-agent-go/model"
    "trpc.group/trpc-go/trpc-agent-go/model/openai"
    "trpc.group/trpc-go/trpc-agent-go/runner"
    "trpc.group/trpc-go/trpc-agent-go/session/inmemory"
)
```

**Key pattern — tRPC-agent-go uses the "functional options" pattern:**
Functions like `llmagent.New()` take a name, then variadic options:
```go
llmagent.New("hugo",
    llmagent.WithModel(myModel),
    llmagent.WithInstruction("You are HUGO..."),
)
```
Each `With...` function returns an option that configures one aspect.
This is a very common Go pattern for building complex objects without
huge constructors.

**Anthropic model setup through tRPC-agent-go:**
tRPC-agent-go wraps all providers behind the OpenAI-compatible interface.
For Anthropic, you set the base URL and variant:
```go
mdl := openai.New(cfg.ModelName,
    openai.WithAPIKey(cfg.APIKey),
    openai.WithBaseURL("https://api.anthropic.com/v1"),
    openai.WithVariant("anthropic"),
)
```

**The runner:**
```go
r := runner.NewRunner("hugo", myAgent,
    runner.WithSessionService(inmemory.NewService()),
)
```

### 8c: Wire it into the chat loop

**File: `cmd/hugo/main.go`**

Update your main to:

1. Load config
2. Call `agent.NewAgent(cfg)` — get back the runner
3. Define `userID` and `sessionID` as constants (just `"user-1"` and `"session-1"` for now)
4. In the chat loop, instead of echoing, call the runner:

```go
// Create a user message
msg := model.NewUserMessage(input)

// Run the agent — returns an event channel
events, err := r.Run(ctx, userID, sessionID, msg)
if err != nil {
    fmt.Fprintf(os.Stderr, "Error: %v\n", err)
    continue
}

// Read events and print text
fmt.Print("HUGO: ")
for evt := range events {
    if evt.Error != nil {
        fmt.Fprintf(os.Stderr, "\nError: %s\n", evt.Error.Message)
        break
    }
    // Streaming: check Delta.Content for partial text
    if len(evt.Choices) > 0 && evt.Choices[0].Delta.Content != "" {
        fmt.Print(evt.Choices[0].Delta.Content)
    }
}
fmt.Println()    // newline after response
```

**You'll also need a `context.Context`:**
```go
import "context"

ctx := context.Background()
```

Context is Go's mechanism for cancellation and deadlines. `Background()` returns
a root context that never cancels — fine for now. We'll use cancellable contexts
in the voice pipeline later.

**Book:** Chapter 14 (The Context — important chapter, read when ready)

### 8d: Test it

```bash
# Make sure .env has your real ANTHROPIC_API_KEY
go run ./cmd/hugo
```

You should be able to have a multi-turn conversation. The agent remembers
context within the session because the runner persists events to the session store.

**Checkpoint:** A working text chat with Claude. This is Phase 1 complete.

---

## What You've Learned

By the end of these 8 steps, you've used:

| Go Concept | Where You Used It |
|---|---|
| Packages & imports | Every file |
| `func main()` | `cmd/hugo/main.go` |
| Structs | `Config` |
| Functions & return values | `NewDefaultConfig()`, `LoadConfig()` |
| Error handling (`if err != nil`) | `LoadConfig()`, runner calls |
| Interfaces | Greeter exercise (and implicitly, the entire framework) |
| Loops & control flow | Chat loop |
| Standard library (`fmt`, `bufio`, `os`, `strings`) | Throughout |
| Third-party dependencies (`go get`) | godotenv, tRPC-agent-go |
| Channels (`for evt := range events`) | Consuming agent events |
| Context | `context.Background()` |
| Functional options pattern | Agent/runner configuration |

---

---
---

# Phase 2: Adding Tools

Phase 1 gave you a chatting agent. Phase 2 gives it **capabilities** — tools
the agent can call to do real work. This is what separates a chatbot from an agent.

New Go concepts in this phase:
- **Generics** — type parameters like `[I, O any]`
- **JSON struct tags** — `json:"field_name"` and `jsonschema:"description=..."`
- **Slices** — `[]tool.Tool` — Go's dynamic arrays
- **The `time` package** — standard library time handling

**Book:** Chapter 8 (Generics), Chapter 12 (JSON — The Encoding Ecosystem)

---

## Step 9: Understanding Generics and Struct Tags

**Goal:** Learn the two Go features that make function tools work.

### Generics

Go 1.18 added generics. A generic function has **type parameters** in square brackets:

```go
func Print[T any](val T) {
    fmt.Println(val)
}

Print[string]("hello")   // T = string
Print[int](42)            // T = int
Print("hello")            // Go can infer T = string, brackets optional
```

`any` is a **type constraint** — it means "any type at all." You can also write
more restrictive constraints, but `any` is what tRPC-agent-go uses for tools.

`NewFunctionTool` is generic over two types:
```go
func NewFunctionTool[I, O any](
    fn func(context.Context, I) (O, error),
    opts ...Option,
) *FunctionTool[I, O]
```

- `I` = the input struct (what the LLM sends as tool arguments)
- `O` = the output struct (what the tool returns to the LLM)
- The framework auto-generates JSON schemas from `I` and `O` using reflection

You define the structs, write the function, and the framework handles
serialization/deserialization automatically.

### Struct Tags

Go struct fields can have **tags** — metadata strings that libraries read at runtime:

```go
type WeatherArgs struct {
    City    string `json:"city" jsonschema:"description=City name,required"`
    Unit    string `json:"unit" jsonschema:"description=Temperature unit,enum=celsius,enum=fahrenheit"`
}
```

Two tag systems are in play:
- **`json:"city"`** — tells `encoding/json` to use `"city"` as the JSON key
  (instead of `"City"`). This is what the LLM sees and produces.
- **`jsonschema:"description=...,required"`** — tells tRPC-agent-go's schema
  generator to add a description and mark the field as required in the JSON schema
  sent to the LLM.

Without the `json` tag, Go uses the field name as-is (`City`). The LLM would
need to produce `{"City": "Tokyo"}` instead of `{"city": "tokyo"}`. Convention
is lowercase JSON keys.

### Slices

A **slice** is Go's dynamic array. You'll use one to pass tools to the agent:

```go
// Slice literal
tools := []tool.Tool{timeTool, weatherTool}

// Append to a slice
tools = append(tools, anotherTool)

// Iterate a slice
for i, t := range tools {
    fmt.Printf("Tool %d: %s\n", i, t.Declaration().Name)
}
```

Slices are passed by reference (technically by header), so appending inside a
function modifies the original. But for our use case, we just build the slice
and pass it to `WithTools`.

**Book:** Chapter 3 (Composite Types — slice section)

---

## Step 10: Your First Tool — Current Time

**Goal:** Create a tool that returns the current date and time.

This is the simplest possible tool — no input fields, one output field.
Perfect for understanding the pattern.

**Task:** Create `internal/agent/tools.go` and define a time tool.

**What you need to write:**

1. An input struct — empty, since this tool takes no arguments:
   ```go
   type TimeInput struct{}
   ```

2. An output struct — one field for the time string:
   ```go
   type TimeOutput struct {
       CurrentTime string `json:"current_time" jsonschema:"description=Current date and time"`
   }
   ```

3. The tool function — takes `context.Context` and input, returns output and error:
   ```go
   func getTime(_ context.Context, _ TimeInput) (TimeOutput, error) {
       return TimeOutput{
           CurrentTime: time.Now().Format(time.RFC1123),
       }, nil
   }
   ```
   Note the `_` for unused parameters — Go requires you to use every variable,
   but `_` is the blank identifier that tells Go "I know I'm not using this."

4. A function that builds and returns the tool:
   ```go
   func NewTimeTool() *function.FunctionTool[TimeInput, TimeOutput] {
       return function.NewFunctionTool(
           getTime,
           function.WithName("current_time"),
           function.WithDescription("Returns the current date and time"),
       )
   }
   ```

**Imports for this file:**
```go
import (
    "context"
    "time"

    "trpc.group/trpc-go/trpc-agent-go/tool/function"
)
```

**Checkpoint:** File compiles — run `go build ./internal/agent/` to check.
No need to run the full program yet.

---

## Step 11: A Second Tool — Calculator

**Goal:** Create a tool with actual input parameters the LLM must provide.

**Task:** In the same `internal/agent/tools.go` file, add a calculator tool.

**What you need to write:**

1. Input struct — the LLM must provide these:
   ```go
   type CalcInput struct {
       Operation string  `json:"operation" jsonschema:"description=Math operation to perform,required,enum=add,enum=subtract,enum=multiply,enum=divide"`
       A         float64 `json:"a" jsonschema:"description=First number,required"`
       B         float64 `json:"b" jsonschema:"description=Second number,required"`
   }
   ```
   Notice `enum=add,enum=subtract,...` — this tells the LLM exactly which
   operations are valid. The LLM sees this in the tool's JSON schema.

2. Output struct:
   ```go
   type CalcOutput struct {
       Result float64 `json:"result" jsonschema:"description=Calculation result"`
       Error  string  `json:"error,omitempty" jsonschema:"description=Error message if operation failed"`
   }
   ```
   The `omitempty` tag means: if `Error` is empty string, don't include it
   in the JSON output at all. Keeps the response clean for the LLM.

3. The tool function — this one has real logic with a `switch` statement:
   ```go
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
   ```

   **Why return `CalcOutput{Error: ...}, nil` instead of `CalcOutput{}, error`?**
   The second `error` return is for *system failures* (network down, panic).
   A "division by zero" is a *tool-level result* the LLM should handle — so we
   put it in the output struct. If you return a Go error, the framework treats it
   as a system failure and the LLM may not see a useful message.

4. The constructor:
   ```go
   func NewCalcTool() *function.FunctionTool[CalcInput, CalcOutput] {
       return function.NewFunctionTool(
           calculate,
           function.WithName("calculator"),
           function.WithDescription("Performs basic math: add, subtract, multiply, divide"),
       )
   }
   ```

**Checkpoint:** `go build ./internal/agent/` compiles clean.

---

## Step 12: Registering Tools with the Agent

**Goal:** Wire your tools into the agent so the LLM can call them.

**Task:** Modify `internal/agent/hugo.go` to accept tools.

1. Import the `tool` package:
   ```go
   "trpc.group/trpc-go/trpc-agent-go/tool"
   ```

2. In your `NewRunner` function, build the tools and pass them to the agent:
   ```go
   tools := []tool.Tool{
       NewTimeTool(),
       NewCalcTool(),
   }

   agent := llmagent.New("hugo",
       llmagent.WithModel(mdl),
       llmagent.WithInstruction("You are HUGO..."),
       llmagent.WithGenerationConfig(genConfig),
       llmagent.WithTools(tools),
   )
   ```

That's it. The framework handles:
- Sending the tool schemas to the LLM in every request
- Parsing the LLM's tool call responses
- Calling your Go function with the deserialized input
- Sending the output back to the LLM
- Looping until the LLM gives a final text response

**Checkpoint:** `go build ./cmd/hugo` compiles.

---

## Step 13: Testing Tool Calls

**Goal:** Verify the agent actually uses your tools.

**Task:** Run `go run ./cmd/hugo` and try these prompts:

```
You: What time is it?
```
The agent should call `current_time` and tell you the time.

```
You: What is 42 * 17?
```
The agent should call `calculator` with `{"operation": "multiply", "a": 42, "b": 17}`.

```
You: What is 100 divided by 0?
```
The agent should call `calculator` and handle the error gracefully.

```
You: What time is it and what is 2 + 2?
```
The agent might call both tools (or call them sequentially). Watch the behavior.

**Observing tool calls:** Right now you can't see when the agent calls a tool
because we only print streaming text chunks. Let's fix that.

---

## Step 14: Displaying Tool Calls in the CLI

**Goal:** Show tool call events in the terminal so you can see the agent thinking.

**Concepts:**
- The event stream contains different event types — not just text
- Tool call events have `ToolCalls` on the message
- Tool result events have `Role == "tool"`

**Task:** Update the event loop in `cmd/hugo/main.go` to show tool activity.

Right now you have:
```go
for event := range events {
    if event.Object == "chat.completion.chunk" {
        fmt.Print(event.Choices[0].Delta.Content)
    }
}
```

Expand this to also check for tool calls and results. The events you care about:

```go
for event := range events {
    if len(event.Choices) == 0 {
        continue
    }

    choice := event.Choices[0]

    // Streaming text — the agent speaking
    if choice.Delta.Content != "" {
        fmt.Print(choice.Delta.Content)
    }

    // Tool call — the agent decided to use a tool
    if len(choice.Message.ToolCalls) > 0 {
        for _, tc := range choice.Message.ToolCalls {
            fmt.Printf("\n  [tool] %s(%s)\n", tc.Function.Name, tc.Function.Arguments)
        }
    }

    // Tool result — a tool returned its output
    if choice.Message.Role == "tool" {
        fmt.Printf("  [result] %s\n", choice.Message.Content)
    }
}
```

**Why check both `Delta.Content` and `Message.ToolCalls`?**
During streaming, text arrives in `Delta` (partial chunks). Tool calls and
results arrive in `Message` (complete objects). The tRPC-agent-go event
stream mixes both — your consumer needs to handle each type.

**Checkpoint:** When you ask "what time is it?", you should see something like:
```
You: what time is it?
  [tool] current_time({})
  [result] {"current_time":"Thu, 06 Mar 2026 10:30:00 EST"}
The current time is Thursday, March 6th, 2026 at 10:30 AM EST.
```

This is also a preview of the voice pipeline's event consumer from Section 3
of the plan — it does the same thing but speaks instead of printing.

---

## Step 15: Adding a Stub Robot Tool (Optional)

**Goal:** Practice the pattern by adding a mock robot tool.

This previews Phase 5 without needing real hardware. The tool returns fake
data but proves the agent can reason about robot actions.

**Task:** Add a `look_at` tool to `internal/agent/tools.go`:

1. Input:
   ```go
   type LookAtInput struct {
       Direction string `json:"direction" jsonschema:"description=Direction to look,required,enum=left,enum=right,enum=up,enum=down,enum=center"`
   }
   ```

2. Output:
   ```go
   type LookAtOutput struct {
       Status    string `json:"status"`
       Direction string `json:"direction"`
   }
   ```

3. Function (stub — no real robot):
   ```go
   func lookAt(_ context.Context, args LookAtInput) (LookAtOutput, error) {
       // In Phase 5 this will call robotClient.Goto()
       return LookAtOutput{
           Status:    "moved",
           Direction: args.Direction,
       }, nil
   }
   ```

4. Register it alongside the other tools in `hugo.go`.

**Test it:**
```
You: Look to your left
  [tool] look_at({"direction":"left"})
  [result] {"status":"moved","direction":"left"}
I've turned to look to my left.
```

---

## What You've Learned in Phase 2

| Go Concept | Where You Used It |
|---|---|
| Generics (`[I, O any]`) | `NewFunctionTool[TimeInput, TimeOutput]` |
| Struct tags (`json`, `jsonschema`) | All input/output structs |
| Slices (`[]tool.Tool`) | Tool list passed to `WithTools` |
| `switch` statement | Calculator operation dispatch |
| Blank identifier (`_`) | Unused context/input params |
| `omitempty` JSON tag | CalcOutput.Error field |
| `time` package | `time.Now().Format(time.RFC1123)` |
| Multiple return values | `(CalcOutput, error)` |

---

---
---

# Phase 3: WebSocket Server

Phase 2 gave you tools. Phase 3 puts them behind an HTTP server so any client
(browser, mobile app, another service) can talk to HUGO over WebSocket.

New Go concepts in this phase:
- **`net/http`** — Go's built-in HTTP server (no framework needed)
- **gorilla/websocket** — WebSocket upgrade and message handling
- **Goroutines** — `go func() { ... }()` for handling concurrent connections
- **`encoding/json`** — `json.Marshal` / `json.Unmarshal`
- **Pointers** — `*Conn`, `&msg` — when and why
- **`sync.Mutex`** — protecting shared state across goroutines
- **`defer`** — cleanup that runs when a function exits

**Book:** Chapter 5 (Functions — defer section), Chapter 7 (Pointers),
Chapter 12 (JSON), Chapter 14 (Concurrency — goroutines, mutexes)

---

## Step 16: Understanding `net/http`

**Goal:** Learn how Go serves HTTP — it's simpler than you'd expect.

Go's standard library includes a production-grade HTTP server. No Express,
no Flask, no framework. Just `net/http`.

**Core idea:** An HTTP server maps URL patterns to **handler functions**.
A handler function has this signature:

```go
func(w http.ResponseWriter, r *http.Request)
```

- `w` — write your response here (status code, headers, body)
- `r` — the incoming request (method, URL, headers, body)

**Minimal server:**
```go
package main

import (
    "fmt"
    "net/http"
)

func main() {
    http.HandleFunc("/hello", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintf(w, "Hello from HUGO")
    })

    fmt.Println("Listening on :8080")
    http.ListenAndServe(":8080", nil)
}
```

`ListenAndServe` blocks forever — it runs the server on the current goroutine.
Every incoming request is handled on its own goroutine automatically.
You don't need to spawn goroutines for request handling — Go does it for you.

**`http.ServeMux`** is the router (pattern → handler). When you pass `nil` to
`ListenAndServe`, it uses the global default `http.DefaultServeMux`. For
production code, create your own:

```go
mux := http.NewServeMux()
mux.HandleFunc("/hello", helloHandler)
mux.HandleFunc("/ws", wsHandler)
http.ListenAndServe(":8080", mux)
```

This is important — the default global mux is shared across your entire process.
Using your own mux keeps things isolated.

---

## Step 17: Understanding WebSockets and gorilla/websocket

**Goal:** Learn how WebSocket connections work in Go.

### What's a WebSocket?

HTTP is request-response: client asks, server answers, connection done.
WebSocket starts as HTTP, then **upgrades** to a persistent bidirectional
connection. Both sides can send messages at any time. Perfect for chat.

### gorilla/websocket

The standard Go WebSocket library. Three things to know:

**1. Upgrader** — converts an HTTP request into a WebSocket connection:
```go
var upgrader = websocket.Upgrader{
    CheckOrigin: func(r *http.Request) bool {
        return true // allow all origins in dev
    },
}

func wsHandler(w http.ResponseWriter, r *http.Request) {
    conn, err := upgrader.Upgrade(w, r, nil)
    if err != nil {
        return // upgrade failed, HTTP error already sent
    }
    defer conn.Close()
    // conn is now a *websocket.Conn — full duplex
}
```

**2. Reading and writing** — one reader goroutine, one writer goroutine:
```go
// Reading (blocks until message arrives)
_, msg, err := conn.ReadMessage()

// Writing JSON (sends a TextMessage frame)
conn.WriteJSON(someStruct)
```

**3. Thread safety rule:**
- ONE goroutine may read at a time
- ONE goroutine may write at a time
- One reader + one writer concurrently IS safe
- Two writers concurrently is NOT safe

This means: if you want to send messages from multiple goroutines (e.g. streaming
agent events while also sending keepalives), you must serialize writes through
a channel. We'll do this with a `writeCh`.

---

## Step 18: Understanding Pointers

**Goal:** Know when you're working with values vs references.

You'll encounter pointers constantly in Phase 3: `*websocket.Conn`,
`*http.Request`, `*WSMessage`.

**The basics:**
```go
x := 42       // x is an int, value is 42
p := &x       // p is a *int (pointer to int), holds x's memory address
fmt.Println(*p) // 42 — *p "dereferences" the pointer, gets the value

*p = 100       // changes x through the pointer
fmt.Println(x)  // 100
```

**Why pointers matter:**
- Go is pass-by-value. Without pointers, functions get copies of structs.
- `conn *websocket.Conn` means you're sharing the SAME connection object,
  not a copy. Calling `conn.WriteJSON()` writes to the real connection.
- `&msg` means "give me a pointer to msg" — `json.Unmarshal` needs a pointer
  so it can write into your struct.

**When you see `*Type` in a function signature**, it means "I need the real
thing, not a copy." When you see `&value`, it means "here's a pointer to this."

**Book:** Chapter 6 (Pointers)

---

## Step 19: Define the WebSocket Message Protocol

**Goal:** Design the JSON messages that flow between client and server.

**Task:** Create `internal/server/messages.go` with the message types.

Before writing server code, define what the wire protocol looks like. Both
sides need to agree on message shapes.

**Client → Server (incoming):**
```go
// ClientMessage is what the client sends us.
type ClientMessage struct {
    Type string `json:"type"` // "message"
    Text string `json:"text"` // user's input text
}
```

**Server → Client (outgoing):**
```go
// ServerMessage is what we send to the client.
type ServerMessage struct {
    Type   string `json:"type"`             // "chunk", "tool_call", "tool_result", "done", "error"
    Text   string `json:"text,omitempty"`   // for "chunk"
    Tool   string `json:"tool,omitempty"`   // for "tool_call", "tool_result"
    Args   string `json:"args,omitempty"`   // for "tool_call" — raw JSON string
    Result string `json:"result,omitempty"` // for "tool_result"
    Error  string `json:"error,omitempty"`  // for "error"
}
```

This maps directly to the WS protocol in the plan (Section 7, Phase 3).

**Why raw `string` for Args/Result instead of `map[string]any`?**
The tool arguments and results come from tRPC-agent-go as JSON strings already.
Passing them as strings avoids double-encoding. The client can parse them if needed.

**Imports:** Just `package server` — no imports needed for struct definitions.

**Checkpoint:** `go build ./internal/server/` compiles.

---

## Step 20: Build the Server

**Goal:** Create the HTTP server with a WebSocket endpoint.

**Task:** Create `internal/server/server.go`.

This file needs:
1. A `Server` struct that holds the runner and server config
2. A constructor `New(r runner.Runner, port string) *Server`
3. A `Start()` method that starts listening
4. A WebSocket handler function

**What to write:**

```go
package server

import (
    "fmt"
    "net/http"

    "github.com/gorilla/websocket"
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
```

**`return &Server{...}`** — this returns a pointer to the struct. Why?
- The `Server` struct is mutable (the runner processes requests)
- If we returned `Server` (no pointer), callers would get a copy
- With `*Server`, everyone shares the same instance
- Convention: constructors return `*T` when the struct is used with methods

Now add the `Start` method:

```go
// Start begins listening for HTTP and WebSocket connections.
func (s *Server) Start() error {
    mux := http.NewServeMux()

    mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
        fmt.Fprintf(w, "ok")
    })

    mux.HandleFunc("/ws", s.handleWS)

    fmt.Printf("HUGO server listening on :%s\n", s.port)
    return http.ListenAndServe(":"+s.port, mux)
}
```

**`(s *Server)` is a method receiver** — it attaches `Start` to the `Server` type.
Inside the method, `s` is the server instance (like `self` or `this`).
`s.runner` accesses the runner, `s.handleWS` refers to another method on Server.

**Checkpoint:** This won't compile yet — `s.handleWS` doesn't exist. That's Step 21.

---

## Step 21: The WebSocket Handler

**Goal:** Handle a WebSocket connection — read messages, run the agent, write responses.

**Task:** Add the `handleWS` method to `internal/server/server.go`.

This is the core logic. For each WebSocket connection:
1. Upgrade HTTP → WebSocket
2. Start a write goroutine (owns all writes to the connection)
3. Read loop: read client messages, run the agent, send events through the write channel

**Concepts in play:**
- **`defer`** — schedules cleanup code to run when the function returns,
  no matter how it returns (normal exit, error, panic). Stack-based: last
  defer runs first.
- **`go func() { ... }()`** — launches a goroutine (lightweight concurrent thread).
  The `()` at the end immediately invokes the anonymous function.
- **Channels** — `writeCh chan ServerMessage` serializes writes to the connection.
  The write goroutine is the only thing that calls `conn.WriteJSON`. Everyone
  else sends to the channel.

```go
func (s *Server) handleWS(w http.ResponseWriter, r *http.Request) {
    conn, err := upgrader.Upgrade(w, r, nil)
    if err != nil {
        return
    }
    defer conn.Close()

    // Write channel — all outgoing messages go through here.
    // Buffered (16) so the agent doesn't block if the client is slow.
    writeCh := make(chan ServerMessage, 16)

    // Writer goroutine — the ONLY goroutine that writes to conn.
    go func() {
        for msg := range writeCh {
            if err := conn.WriteJSON(msg); err != nil {
                return
            }
        }
    }()

    // Read loop — runs on this goroutine (the HTTP handler goroutine).
    for {
        var msg ClientMessage
        if err := conn.ReadJSON(&msg); err != nil {
            break // client disconnected or bad message
        }

        if msg.Type != "message" || msg.Text == "" {
            continue
        }

        // Process the message — run the agent and stream results.
        s.processMessage(r.Context(), msg.Text, writeCh)
    }

    close(writeCh) // signals the writer goroutine to exit
}
```

**`conn.ReadJSON(&msg)`** — the `&` passes a pointer to `msg` so that
`ReadJSON` can fill in the fields. Without `&`, it would get a copy and
your `msg` variable would stay empty.

**`make(chan ServerMessage, 16)`** — creates a buffered channel. Up to 16
messages can sit in the channel before a sender blocks. This prevents the
agent from stalling if the network is slow.

**`close(writeCh)`** — closing a channel causes the `for msg := range writeCh`
loop in the writer goroutine to exit. This is how you cleanly shut down
the writer when the read loop ends.

---

## Step 22: Processing Messages (Agent Integration)

**Goal:** Wire the agent runner into the WebSocket handler.

**Task:** Add the `processMessage` method to `internal/server/server.go`.

This is where you connect the WebSocket to the agent runner — the same
event loop from your CLI, but writing to a channel instead of stdout.

```go
import (
    "context"
    "trpc.group/trpc-go/trpc-agent-go/model"
)

func (s *Server) processMessage(ctx context.Context, text string, writeCh chan<- ServerMessage) {
    events, err := s.runner.Run(
        ctx,
        "user-001",     // TODO: per-connection user ID
        "session-001",  // TODO: per-connection session ID
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

        // Streaming text chunk
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
                    Args: tc.Function.Arguments,
                }
            }
        }

        // Tool result
        if choice.Message.Role == "tool" {
            writeCh <- ServerMessage{
                Type:   "tool_result",
                Tool:   choice.Message.Name,
                Result: choice.Message.Content,
            }
        }
    }

    // Signal that the response is complete
    writeCh <- ServerMessage{Type: "done"}
}
```

**`chan<- ServerMessage`** — the `<-` arrow means this is a **send-only channel**.
The function can only write to it, not read from it. This is a type-safety feature:
it prevents `processMessage` from accidentally reading messages meant for the
write goroutine. Compare:
- `chan ServerMessage` — bidirectional (read and write)
- `chan<- ServerMessage` — send only
- `<-chan ServerMessage` — receive only

You saw `<-chan` in Phase 1 with the events channel. Now you see `chan<-` for the other direction.

**Book:** Chapter 12 (Concurrency — channel direction section)

---

## Step 23: Wire It Into main.go

**Goal:** Add a `serve` subcommand to start the HTTP server.

**Task:** Update `cmd/hugo/main.go` to accept a command-line argument.

**Concepts:**
- `os.Args` is a slice of command-line arguments (`os.Args[0]` is the program name)
- We'll check if `os.Args[1]` is `"serve"` — if so, start the server instead of CLI

```go
import (
    "hugo/internal/server"
)

func main() {
    _ = godotenv.Load(".env.local")

    cfg, err := agent.LoadConfig()
    if err != nil {
        fmt.Fprintf(os.Stderr, "Error: %v\n", err)
        os.Exit(1)
    }

    r := agent.NewRunner(cfg)

    // Check for subcommand
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

    // Default: CLI mode (your existing chat loop)
    ctx := context.Background()
    scanner := bufio.NewScanner(os.Stdin)
    // ... rest of your existing CLI loop ...
}
```

**Don't forget to add the gorilla/websocket dependency:**
```bash
go get github.com/gorilla/websocket
```

**Checkpoint:** `go build ./cmd/hugo` compiles.

---

## Step 24: Test the WebSocket Server

**Goal:** Verify the server works with a real WebSocket client.

**Run the server:**
```bash
go run ./cmd/hugo serve
```

You should see: `HUGO server listening on :8080`

**Test health endpoint:**
```bash
curl http://localhost:8080/health
# Should print: ok
```

**Test WebSocket with websocat** (install: `brew install websocat`):
```bash
websocat ws://localhost:8080/ws
```

Then type JSON messages:
```json
{"type": "message", "text": "What time is it?"}
```

You should see streaming responses:
```json
{"type":"tool_call","tool":"current_time","args":"{}"}
{"type":"tool_result","tool":"current_time","result":"{\"current_time\":\"...\"}"}
{"type":"chunk","text":"The "}
{"type":"chunk","text":"current "}
{"type":"chunk","text":"time is..."}
{"type":"done"}
```

**Test from a browser console:**
```javascript
const ws = new WebSocket("ws://localhost:8080/ws");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
ws.onopen = () => ws.send(JSON.stringify({type: "message", text: "Hello HUGO!"}));
```

**Checkpoint:** Full conversation works over WebSocket. CLI mode still works too.

---

## Step 25: Add Per-Connection Sessions (Optional)

**Goal:** Give each WebSocket connection its own session so conversations don't mix.

Right now every connection shares `"user-001"` / `"session-001"`. If two browsers
connect, they'd share conversation history.

**Task:** Generate a unique session ID when a WebSocket connects.

You'll need the `uuid` package — but Go has a simpler built-in option for this:

```go
import "crypto/rand"

func generateID() string {
    b := make([]byte, 16)
    rand.Read(b)
    return fmt.Sprintf("%x", b)
}
```

Then in `handleWS`, generate the IDs at connection time and pass them to
`processMessage`. You can store them in the `handleWS` function scope —
they live for the duration of the WebSocket connection.

```go
func (s *Server) handleWS(w http.ResponseWriter, r *http.Request) {
    // ... upgrade ...

    userID := "user-" + generateID()
    sessionID := "session-" + generateID()

    // ... in the read loop:
    s.processMessage(r.Context(), msg.Text, writeCh, userID, sessionID)
}
```

Update `processMessage` to accept `userID` and `sessionID` parameters instead
of hardcoded strings.

---

## What You've Learned in Phase 3

| Go Concept | Where You Used It |
|---|---|
| `net/http` server | `http.NewServeMux()`, `ListenAndServe` |
| Handler functions | `func(w http.ResponseWriter, r *http.Request)` |
| gorilla/websocket | `Upgrader.Upgrade()`, `ReadJSON`, `WriteJSON` |
| Goroutines | `go func() { ... }()` for the write goroutine |
| Channels (buffered) | `make(chan ServerMessage, 16)` |
| Channel direction | `chan<- ServerMessage` (send-only) |
| `defer` | `defer conn.Close()` |
| `close()` | Signaling the writer goroutine to exit |
| Pointers | `*Server`, `&msg`, `*websocket.Conn` |
| Method receivers | `(s *Server)` on Start, handleWS, processMessage |
| `os.Args` | Subcommand routing |
| `crypto/rand` | Generating connection IDs |
| JSON marshal/unmarshal | `ReadJSON(&msg)`, `WriteJSON(msg)` |

---

## Next Steps

Phase 4 (Voice Pipeline) introduces:
- **`errgroup`** — managing multiple goroutines with error propagation
- **`context.WithCancel`** — cancellable contexts for barge-in
- **`select`** — multiplexing across multiple channels
- **`sync.Mutex`** — protecting the speech queue
- **CGO** — calling C libraries (for Silero VAD and whisper.cpp)
- **`io.Pipe`** — streaming audio between goroutines

Phase 4 is a significant step up in complexity. Make sure you're comfortable
with goroutines, channels, and `defer` before starting it.
