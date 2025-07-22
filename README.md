# HUGO Project

This project includes vLLM built from source for Apple Silicon (M4 Pro).

## Prerequisites

- macOS Sonoma or later
- Python 3.12 (vLLM doesn't support Python 3.13 yet)
- uv package manager
- Homebrew (for installing build tools)
- Xcode Command Line Tools

## Setup Instructions

### 1. Install Build Dependencies

```bash
# Install Ninja and CMake if not already installed
brew install ninja cmake
```

### 2. Set up Python Environment

```bash
# Create a virtual environment with Python 3.12
uv venv --python 3.12

# Activate the virtual environment
source .venv/bin/activate
```

### 3. Clone and Build vLLM

```bash
# Clone vLLM repository
git clone https://github.com/vllm-project/vllm.git dependencies

# Navigate to dependencies folder
cd dependencies

# Set environment variable for CPU build
export VLLM_TARGET_DEVICE=cpu

# Install CPU requirements
uv pip install -r requirements/cpu.txt --index-strategy unsafe-best-match

# Build and install vLLM
uv pip install -e .
```

### 4. Verify Installation

```bash
python -c "import vllm; print(f'vLLM version: {vllm.__version__}')"
```

## Important Notes

- vLLM on macOS Apple Silicon runs in CPU mode only
- The build process may take several minutes
- Make sure to use Python 3.12 as vLLM doesn't support Python 3.13 yet
- The `dependencies/` folder is excluded from git tracking

## Troubleshooting

If you encounter build errors:

1. Ensure Xcode Command Line Tools are properly installed:
   ```bash
   xcode-select --install
   ```

2. If you see C++ header errors, try reinstalling Command Line Tools:
   ```bash
   sudo rm -rf /Library/Developer/CommandLineTools
   xcode-select --install
   ```

3. Make sure you're using Python 3.12:
   ```bash
   python --version  # Should show 3.12.x
   ```