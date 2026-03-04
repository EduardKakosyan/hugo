# Learning Go Through HUGO — Step-by-Step Guide

This guide walks you through Go from zero, building toward Phase 1 of HUGO.
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

## Next Steps

After Phase 1 is working, you'll tackle Phase 2 (tools), which introduces:
- **Generics** — `function.NewFunctionTool[I, O]`
- **JSON struct tags** — `json:"field_name"`
- **Method receivers** — attaching behavior to structs
- **Slices** — Go's dynamic arrays

But first — get Phase 1 running. Take your time with each step.
