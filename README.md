# OpenDialogum (GUM)

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![CodeQL](https://github.com/ArnavS-22/opendialogum/actions/workflows/codeql.yml/badge.svg)

**OpenDialogum** (formerly GUM) is a General User Modeling library designed to enable clarification in AI systems. It provides tools for observing user behavior, maintaining propositions about user state, and detecting when clarification is needed.

## Features

- **Observation Tracking**: Monitors user interactions across applications.
- **Proposition Management**: Maintains a database of "propositions" (beliefs about the user).
- **Clarification Detection**: Automatically detects when user intent is ambiguous and generates clarifying questions.
- **Privacy-First**: a strict local-storage policy. All data is stored locally in `~/.cache/gum/gum.db`.
> [!IMPORTANT]
> **Security Notice**: Data is currently stored in a standard SQLite database. While this ensures data stays on your machine, it is not encrypted at rest. Users are responsible for securing their local environment (e.g., using Full Disk Encryption).


## Installation

```bash
git clone https://github.com/ArnavS-22/opendialogum.git
cd opendialogum
pip install -e .
```

## Quick Start

### Running the CLI

OpenDialogum comes with a CLI tool `gum`.

```bash
# Start tracking
gum start --user "My Name"

# Detect clarification needs
gum detect
```

### Library Usage

```python
import asyncio
from gum import gum
from gum.models import Proposition

async def main():
    async with gum(user_name="User", model="gpt-4") as g:
        # Your custom logic here
        pass

if __name__ == "__main__":
    asyncio.run(main())
```

## Dashboard

The project includes a visualization dashboard.

```bash
# Start the backend API
uvicorn dashboard.api_server:app --host 0.0.0.0 --port 8000

# Start the frontend (in a separate terminal)
cd dashboard
npm install
npm run dev
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

See [SECURITY.md](SECURITY.md) for our security policy and reporting process.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
