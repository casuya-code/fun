# Contributing to BetPicks

## Development Setup
1. Clone the repository
2. Install dependencies: pip install -r requirements.txt
3. Start the server: uvicorn app.main:app --host 127.0.0.1 --port 8000
4. Run tests: pytest

## Commit Message Convention
- eat: New feature
- ix: Bug fix
- chore: Maintenance
- docs: Documentation

## Pull Request Process
1. Create a feature branch: git checkout -b feature/your-feature
2. Make your changes
3. Run pytest to ensure all tests pass
4. Commit with descriptive message
5. Push and create a Pull Request

## Code Style
- Follow PEP 8 Python style guidelines
- Use type hints where appropriate
- Keep commit messages concise but descriptive

## Reporting Issues
- Use the issue tracker to report bugs or request features
- Include steps to reproduce, expected vs actual behavior
- Check existing issues before creating new ones

