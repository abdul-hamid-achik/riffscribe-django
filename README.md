# 🎸 RiffScribe

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-green)](https://www.djangoproject.com/)
[![HTMX](https://img.shields.io/badge/HTMX-1.9-purple)](https://htmx.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

**RiffScribe** is an AI-powered guitar tab transcription tool that converts audio recordings into accurate guitar tablature. Built with Django and HTMX for a smooth, server-rendered experience with modern interactivity.

## ✨ Features

- 🎵 **Audio Analysis**: Automatic tempo, key, and instrument detection
- 🤖 **Whisper AI Integration**: Enhanced transcription accuracy using OpenAI's Whisper AI
- 🎸 **Tab Generation**: Convert audio to guitar tablature notation with playability-aware fingering
- 🎯 **Multiple Difficulty Variants**: Generate Easy, Balanced, Technical, and Original fingering arrangements
- 📊 **Playability Metrics**: Analyze fret spans, position changes, and technique complexity
- 🎼 **Chord Detection**: AI-powered chord progression identification and analysis
- 📊 **Real-time Processing**: Live status updates during transcription with AI enhancement indicators
- 📁 **Multiple Formats**: Export to MusicXML, Guitar Pro, PDF, and ASCII tabs
- 🌙 **Modern UI**: Dark theme interface with responsive design
- ⚡ **HTMX Powered**: Server-rendered with dynamic updates, no complex JavaScript

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- uv (Python package manager)
- Node.js 18+ and npm (for Tailwind CSS)
- ffmpeg (for audio processing)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/abdul-hamid-achik/riffscribe-django.git
cd riffscribe-django
```

2. **Install Python dependencies using uv**
```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

3. **Install Node.js dependencies for Tailwind CSS**
```bash
# Install Tailwind and build CSS
npm install
npm run build-css
```

4. **Install ffmpeg** (required for audio processing)
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

5. **Run migrations**
```bash
uv run python manage.py migrate
```

6. **Create a superuser** (optional, for admin access)
```bash
uv run python manage.py createsuperuser
```

7. **Start the development server**
```bash
# For development with auto-reload CSS
npm run watch-css &  # Run Tailwind watcher in background
uv run python manage.py runserver

# Or for production
npm run build-css  # Build minified CSS
uv run python manage.py runserver
```

Visit `http://localhost:8000` to start transcribing!

## 📖 Usage

1. **Upload Audio**: Click "Upload Audio" and select your music file
   - Supported formats: MP3, WAV, M4A, FLAC, OGG
   - Best results with clear guitar recordings

2. **Processing**: Watch real-time analysis of your audio
   - Tempo detection
   - Key estimation
   - Complexity analysis
   - Instrument identification

3. **View Results**: See generated tablature and audio analysis

4. **Export**: Download tabs in your preferred format
   - MusicXML (for music notation software)
   - Guitar Pro (for Guitar Pro software)
   - PDF (for printing)
   - ASCII (for sharing online)

## 🤖 Whisper AI Enhancement

When enabled, RiffScribe uses OpenAI's Whisper AI to significantly improve transcription accuracy and provide additional musical insights:

### Key Benefits

- **Enhanced Accuracy**: Whisper's advanced audio understanding improves note and chord detection
- **Musical Context**: AI provides musical descriptions and genre identification
- **Chord Progressions**: Automatic detection of chord sequences and harmonic analysis
- **Time Signatures**: Better detection of complex rhythmic patterns
- **Tempo Analysis**: More accurate BPM estimation with musical context

### How It Works

1. **Audio Analysis**: Whisper analyzes your audio for musical content and structure
2. **Chord Detection**: Identifies chord progressions and harmonic patterns
3. **Musical Description**: Provides AI-generated descriptions of the musical content
4. **Context Enhancement**: Uses musical understanding to improve basic pitch detection
5. **Fallback Support**: Seamlessly falls back to traditional methods if AI processing fails

### Visual Indicators

- **AI-Enhanced Badge**: Transcriptions processed with Whisper show a green "AI-Enhanced Transcription" badge
- **Chord Count**: Display shows number of detected chord progressions
- **Musical Description**: Brief AI-generated summary of the musical content
- **Processing Status**: Real-time updates show when Whisper analysis is active

## 🎨 Tailwind CSS Setup

RiffScribe uses Tailwind CSS for styling with a custom build process for optimal performance.

### Development

```bash
# Watch for CSS changes during development
npm run watch-css

# Or run both Django and Tailwind watchers
npm run dev &
uv run python manage.py runserver
```

### Production Build

```bash
# Build minified CSS for production
npm run build-css

# Then collect static files for Django
uv run python manage.py collectstatic
```

### Custom Tailwind Classes

The project includes custom color schemes and components:

- **NYT Theme Colors**: `text-nyt-black`, `bg-nyt-gray-dark`, etc.
- **Musical Colors**: `text-musical-gold`, `bg-sheet-cream`, etc.
- **Custom Components**: `.sheet-card`, `.status-badge`, `.btn-primary`
- **Typography**: `font-display` (Playfair), `font-headline` (Crimson), `font-body` (Inter)

Configuration is in `tailwind.config.js` and source styles in `transcriber/static/transcriber/css/input.css`.

## 🏗️ Architecture

```
riffscribe-django/
├── transcriber/          # Main Django app
│   ├── models.py        # Data models (including variant & metrics models)
│   ├── views.py         # View controllers with HTMX endpoints
│   ├── audio_processing.py  # Audio analysis engine
│   ├── ml_pipeline.py   # Enhanced ML pipeline with Whisper integration
│   ├── whisper_service.py   # Whisper AI service wrapper
│   ├── tasks.py         # Celery background processing
│   ├── fingering_optimizer.py  # DP-based fingering optimization
│   ├── variant_generator.py    # Variant generation & metrics
│   ├── management/      # Django management commands
│   └── templates/       # HTMX templates with AI indicators
├── riffscribe/          # Project configuration
├── static/              # CSS and static files
└── media/              # Uploaded files
```

### Technology Stack

- **Backend**: Django 5.2 - Python web framework
- **Frontend**: HTMX + Alpine.js - Modern interactivity without complexity
- **Styling**: Tailwind CSS - Utility-first CSS framework with custom build process
- **Audio Processing**: Librosa - Music and audio analysis
- **AI Enhancement**: OpenAI Whisper - Advanced audio transcription and analysis
- **Guitar Pro Support**: PyGuitarPro - Read/write GP3, GP4, GP5 files
- **Machine Learning**: Basic Pitch - Note detection and pitch estimation
- **Storage**: SQLite (dev) / PostgreSQL (production)

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Django settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (optional, defaults to SQLite)
DATABASE_URL=postgresql://user:pass@localhost/dbname

# Audio processing
MAX_UPLOAD_SIZE=52428800  # 50MB in bytes
PROCESSING_TIMEOUT=300     # seconds

# Whisper AI Integration (optional but recommended)
OPENAI_API_KEY=sk-your-openai-api-key-here
USE_WHISPER=True
WHISPER_MODEL=whisper-1
WHISPER_ENABLE_CHORD_DETECTION=True
```

### Whisper AI Setup

To enable enhanced transcription with OpenAI's Whisper AI:

1. **Get an OpenAI API key** from [OpenAI Platform](https://platform.openai.com/api-keys)
2. **Add to environment variables** in your `.env` file:
   ```env
   OPENAI_API_KEY=sk-your-openai-api-key-here
   USE_WHISPER=True
   WHISPER_ENABLE_CHORD_DETECTION=True
   ```
3. **Install OpenAI SDK** (already included in dependencies):
   ```bash
   uv add openai
   ```

#### Whisper Configuration Options

- `USE_WHISPER`: Enable/disable Whisper AI integration (default: True if API key present)
- `WHISPER_MODEL`: Model to use ('whisper-1' recommended)
- `WHISPER_ENABLE_CHORD_DETECTION`: Enable chord progression analysis (default: True)

Without Whisper, the system falls back to traditional audio processing methods.

### Production Deployment

For production deployment:

1. Set `DEBUG=False` in settings
2. Configure a production database (PostgreSQL recommended)
3. Set up static file serving (WhiteNoise included)
4. Use a production WSGI server (Gunicorn, uWSGI)
5. Configure media file storage (AWS S3, etc.)
6. Set up OpenAI API key for Whisper enhancement

## 🎸 Fingering Variants & Playability System

RiffScribe includes an advanced fingering optimization system that generates multiple difficulty variants for each transcription:

### Variant Presets

- **EASY**: Optimized for beginners with minimal hand stretches and position changes
  - Max chord span: 4 frets
  - Prefers lower fret positions
  - Removes complex techniques (bends, wide slides)
  
- **BALANCED**: A good compromise between playability and accuracy
  - Max chord span: 5 frets
  - Moderate position changes allowed
  - Keeps most techniques intact

- **TECHNICAL**: For advanced players, allowing complex fingerings
  - Max chord span: 7 frets
  - Can use higher positions
  - All techniques preserved

- **ORIGINAL**: Analysis-driven variant based on the audio characteristics
  - Adapts to tempo and pitch distribution
  - Dynamic span constraints

### Management Commands

Generate variants manually using the management command:

```bash
# Generate all variants for a transcription
uv run python manage.py generate_variants <transcription_id>

# Generate specific variant
uv run python manage.py generate_variants <transcription_id> --preset easy

# Regenerate all variants for all completed transcriptions
uv run python manage.py generate_variants all --force

# Dry run to see what would be done
uv run python manage.py generate_variants all --dry-run --verbose
```

### API Endpoints

The system provides HTMX-compatible endpoints for variant management:

- `GET /transcription/<id>/variants/` - List all variants
- `POST /transcription/<id>/variants/select/<variant_id>/` - Select a variant
- `GET /transcription/<id>/variants/preview/<variant_id>/` - Preview variant
- `POST /transcription/<id>/variants/regenerate/` - Regenerate variants
- `GET /transcription/<id>/variants/<variant_id>/stats/` - Get variant statistics
- `GET /transcription/<id>/variants/<variant_id>/export/` - Export specific variant

### Developer Guide

#### Adding New Presets

Edit `transcriber/fingering_optimizer.py`:

```python
FINGERING_PRESETS = {
    "custom": OptimizationWeights(
        w_jump=5,           # Fret jump penalty
        w_string=2.5,       # String change penalty
        w_span=7,           # Chord span penalty
        span_cap=5,         # Maximum allowed chord span
        w_open=1.5,         # Open string bonus
        w_high=1,           # High fret penalty
        pref_fret_center=8, # Preferred fret region center
        w_pos=2,            # Position shift penalty
        w_same=0.7          # Same string bonus
    )
}
```

#### Customizing Metrics

Modify `transcriber/variant_generator.py` to adjust the playability scoring:

```python
playability_score = max(0, min(100,
    100 - (2 * avg_jump)                    # Jump penalty
        - (3 * changes_per_measure)         # Position change penalty
        - (4 * avg_chord_span_over_cap)     # Chord span penalty
        + (open_ratio * 10)                 # Open string bonus
))
```

## 🔐 User Authentication & OAuth Setup

RiffScribe includes a complete user authentication system with email/password login and OAuth support for GitHub and Google.

### Setting up OAuth Providers

#### GitHub OAuth Setup

1. Go to [GitHub Settings > Developer settings > OAuth Apps](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Fill in the application details:
   - **Application name**: RiffScribe
   - **Homepage URL**: `http://localhost:8000` (or your production URL)
   - **Authorization callback URL**: `http://localhost:8000/accounts/github/login/callback/`
4. Click "Register application"
5. Copy the **Client ID** and **Client Secret**
6. Add to your `.env` file:
   ```
   GITHUB_CLIENT_ID=your_client_id_here
   GITHUB_CLIENT_SECRET=your_client_secret_here
   ```

#### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the Google+ API
4. Go to "Credentials" > "Create Credentials" > "OAuth 2.0 Client ID"
5. Configure OAuth consent screen if required
6. Application type: Web application
7. Add authorized redirect URIs:
   - `http://localhost:8000/accounts/google/login/callback/`
8. Copy the **Client ID** and **Client Secret**
9. Add to your `.env` file:
   ```
   GOOGLE_CLIENT_ID=your_client_id_here
   GOOGLE_CLIENT_SECRET=your_client_secret_here
   ```

#### Finalizing OAuth Setup

After adding credentials to `.env`, run:

```bash
# With Docker
docker-compose exec django python manage.py setup_oauth

# Without Docker
uv run python manage.py setup_oauth
```

This command will:
- Configure the site domain
- Set up OAuth providers with your credentials
- Display any additional setup instructions

### User Features

- **User Profiles**: Skill level, preferences, bio, and usage statistics
- **Upload Limits**: 10 uploads/month for free users, unlimited for premium
- **Favorites**: Mark and organize favorite transcriptions
- **Personal Library**: View only your own transcriptions
- **OAuth Integration**: Sign in with GitHub or Google
- **Email Authentication**: Traditional email/password registration

## 🥁 Drum Transcription Support

RiffScribe now includes advanced drum transcription capabilities:

### Features

- **Drum Hit Detection**: Identifies kick, snare, hi-hat, crash, ride, and tom hits
- **Pattern Recognition**: Detects common drum patterns (rock beat, swing, etc.)
- **Fill Detection**: Identifies drum fills and high-activity regions
- **Drum Tab Notation**: Generates standard drum tablature
- **Multi-track Integration**: Automatically processes drum tracks when separated

### Drum Tab Format

```
Tempo: 120 BPM
Time: 4/4

Measure 1:
CR |----------------|  (Crash)
HH |x-x-x-x-x-x-x-x-|  (Hi-hat)
SD |----o-------o---|  (Snare)
BD |o-------o-------|  (Bass drum)
```

### Technical Details

The drum transcriber uses:
- Onset detection for timing
- Spectral analysis for drum type classification
- Beat tracking for tempo and structure
- Pattern matching for common grooves
- Velocity detection for dynamics

## 🎯 Roadmap

- [x] Playability-aware fingering optimization
- [x] Multiple difficulty variants
- [x] Celery for async task processing
- [x] Whisper AI integration for improved transcription
- [x] Multi-track support with source separation
- [x] User authentication and profiles
- [x] OAuth integration (GitHub & Google)
- [x] Drum transcription and notation
- [ ] MIDI export with full drum support
- [ ] Social features (share tabs, collaborate)
- [ ] Mobile app
- [ ] REST API for third-party integrations

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Librosa](https://librosa.org/) for audio processing capabilities
- [HTMX](https://htmx.org/) for making web apps fun again
- [Django](https://www.djangoproject.com/) for the excellent web framework
- The open-source community for inspiration and tools

## 💬 Support

- 🐛 Issues: [GitHub Issues](https://github.com/abdul-hamid-achik/riffscribe-django/issues)
- 💡 Discussions: [GitHub Discussions](https://github.com/abdul-hamid-achik/riffscribe-django/discussions)

---

Built with ❤️ for the music community