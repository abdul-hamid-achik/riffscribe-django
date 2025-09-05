# Cursor Background Agents Configuration

This directory contains the configuration files needed to run **riffscribe-django** with Cursor Background Agents. Background Agents allow you to offload long-running AI coding tasks to cloud environments while you continue working locally.

## 📁 Files Overview

### `environment.json`
The main configuration file that defines:
- **Base Environment**: Uses custom Dockerfile optimized for Django + AI/ML
- **Install Commands**: UV-based dependency management and Django setup
- **Background Processes**: Django dev server, Celery workers, and schedulers
- **Secrets Configuration**: Required environment variables and API keys
- **Port Mappings**: Development server and monitoring interfaces

### `Dockerfile.cursor`
Optimized Docker environment for Background Agents with:
- **Python 3.11**: Base runtime with audio processing libraries
- **UV Package Manager**: Fast Python dependency installation
- **Audio Libraries**: FFmpeg, libsndfile for audio processing
- **ML Dependencies**: PyTorch, librosa for AI transcription
- **Development Tools**: All necessary build tools and utilities

### `setup.sh`
Initialization script that:
- Installs Python dependencies with UV
- Runs Django migrations
- Collects static files
- Creates necessary directories
- Validates the setup

## 🚀 Getting Started

### 1. Enable Background Agents
In Cursor, go to **Settings → Beta** and enable **Background Agents**.

### 2. Configure Secrets
In Cursor **Settings → Background Agents → Secrets**, add the following:

#### Required Secrets:
```bash
SECRET_KEY=your-django-secret-key-here
OPENAI_API_KEY=sk-your-openai-api-key
```

**That's it!** No database URLs needed - PostgreSQL and Redis run embedded in the container.

### 3. Launch Background Agent
1. Open Command Palette (`Cmd+Shift+P`)
2. Run **"Background Agents: Launch"**
3. Select your repository and branch
4. Wait for environment setup (takes 2-5 minutes first time)

## 🔧 Available Commands

The Background Agent environment provides several pre-configured terminals:

### Django Development Server
```bash
uv run python manage.py runserver 0.0.0.0:8000
```
Access at: `http://localhost:8000` (forwarded by Cursor)

### Celery Worker
```bash
uv run celery -A riffscribe worker --loglevel=info --concurrency=2
```
Processes background AI transcription tasks.

### Celery Beat Scheduler
```bash
uv run celery -A riffscribe beat --loglevel=info
```
Handles periodic tasks and cleanup.

### Test Suite
```bash
uv run pytest -v                    # All tests
uv run pytest tests/unit/ -v        # Unit tests only
uv run pytest tests/integration/ -v # Integration tests
uv run pytest tests/e2e/ -v         # End-to-end tests
```

### Django Management
```bash
uv run python manage.py shell           # Django shell
uv run python manage.py migrate         # Run migrations
uv run python manage.py createsuperuser # Create admin user
```

## 🎵 Project Overview

**riffscribe-django** is an AI-powered audio-to-guitar-tab transcription service built with:

- **Django 5.0**: Web framework with HTMX for dynamic UI
- **Celery**: Background task processing for AI transcription
- **PyTorch + Librosa**: Audio processing and ML inference
- **OpenAI API**: Enhanced transcription capabilities
- **PostgreSQL**: Primary database
- **Redis**: Message broker and caching
- **UV**: Modern Python package manager

## 🛠 Development Workflow

### Typical Background Agent Tasks:
1. **Feature Development**: "Add user authentication with social login"
2. **Bug Fixes**: "Fix audio upload validation errors"
3. **Refactoring**: "Optimize Celery task performance"
4. **Testing**: "Add unit tests for new transcription features"
5. **Documentation**: "Update API documentation"

### Best Practices:
- **Commit Frequently**: Background Agents work best with regular commits
- **Clear Instructions**: Provide specific, actionable requirements
- **Test Coverage**: Ensure new features have appropriate tests
- **Environment Parity**: Keep local and agent environments synchronized

## 🔍 Monitoring & Debugging

### Flower (Celery Monitoring)
Access Celery task monitoring at `http://localhost:5555` when Flower is running:
```bash
uv run celery -A riffscribe flower --port=5555
```

### Logs
Background Agents provide real-time logs for:
- Django application server
- Celery worker processes
- Task execution details
- Error traces and debugging info

### Health Checks
Verify environment health:
```bash
uv run python manage.py check --deploy
uv run python -c "import torch; print(f'PyTorch: {torch.__version__}')"
```

## 📊 Resource Usage

### Expected Resources:
- **Memory**: 2-4GB (depending on ML model usage)
- **CPU**: 2-4 cores for optimal performance
- **Storage**: 10-20GB for dependencies and models
- **Network**: High bandwidth for model downloads

### Performance Tips:
- Use Background Agents for CPU-intensive tasks
- Keep model files cached between sessions
- Optimize Celery worker concurrency based on available resources

## 🤝 Collaboration

### Team Workflow:
1. **Setup Once**: Each team member configures their secrets
2. **Shared Environment**: All agents use the same `environment.json`
3. **Consistent Setup**: Docker ensures identical environments
4. **Version Control**: All configuration files are committed to repo

### Integration Points:
- **GitHub**: Automatic PR creation and updates
- **Linear**: Task tracking and progress updates
- **Slack**: Team notifications and collaboration

## 🔐 Security Notes

- **Secrets Encryption**: All secrets are encrypted at rest with KMS
- **Non-root User**: Docker runs with `django` user for security
- **Network Isolation**: Agents run in isolated cloud environments
- **Access Control**: Only authorized team members can launch agents

## 🆘 Troubleshooting

### Common Issues:

#### Database Connection Errors
```bash
# Verify DATABASE_URL is set correctly
echo $DATABASE_URL
# Test connection
uv run python manage.py dbshell
```

#### Missing Dependencies
```bash
# Reinstall dependencies
uv sync --reinstall
# Check UV version
uv --version
```

#### Celery Connection Issues
```bash
# Verify Redis connection
echo $REDIS_URL
# Test Celery
uv run celery -A riffscribe inspect ping
```

### Getting Help:
1. Check Background Agent logs in Cursor
2. Verify all secrets are configured
3. Test commands locally first
4. Contact team leads for infrastructure issues

---

## 🎯 Ready to Rock!

Your Cursor Background Agent environment is now configured for AI-powered audio transcription development. The agents can handle complex tasks like:

- Implementing new ML models
- Optimizing audio processing pipelines
- Building API integrations
- Running comprehensive test suites
- Refactoring large codebases

Happy coding! 🎸✨
