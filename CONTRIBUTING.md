# Contributing to OpenDialogum

Thank you for your interest in contributing to OpenDialogum! We welcome contributions from everyone.

## Getting Started

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** locally:
    ```bash
    git clone https://github.com/your-username/opendialogum.git
    cd opendialogum
    ```
3.  **Create a virtual environment** and install dependencies:
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -e ".[dev]"
    ```

## Development Workflow

1.  **Create a branch** for your feature or bugfix:
    ```bash
    git checkout -b feature/my-new-feature
    ```
2.  **Write code** and add tests.
3.  **Run tests** to ensure everything is working:
    ```bash
    pytest tests/
    ```
4.  **Format your code**:
    ```bash
    black .
    isort .
    ```
5.  **Commit your changes** with descriptive messages.
6.  **Push to your fork** and submit a Pull Request.

## Pull Request Guidelines

-   Fill out the Pull Request Template.
-   Ensure all tests pass.
-   Keep changes focused and atomic.
-   Update documentation if necessary.

## Code Style

-   We use [Black](https://github.com/psf/black) for code formatting.
-   We use [isort](https://github.com/PyCQA/isort) for import sorting.
-   Type hints are encouraged.

## Reporting Bugs

Please use the GitHub Issue Tracker to report bugs. Include:
-   Steps to reproduce the issue.
-   Expected vs. actual behavior.
-   Environment details (OS, Python version).

Thank you for contributing!
