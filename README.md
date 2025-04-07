# ShowRenamer

Automatically rename TV show files using fuzzy search to identify episodes. The application monitors specified directories for new files and renames them according to TVDB data.

## Features

- Automatic TV show file renaming using TVDB API
- Directory monitoring with automatic file processing
- Retry mechanism for failed files (once per day)
- Configurable cache with TTL
- Docker support for easy deployment

## Docker Setup (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd ShowRenamer
```

2. Configure your TVDB API key:
```bash
cp .env.example .env
# Edit .env to set your TVDB_API_KEY
```

4. Create required directories:
```bash
mkdir -p config media/incoming media/shows
```

5. Start the application:
```bash
docker-compose up -d
```

The application will:
- Monitor `/media/incoming` for new TV show files
- Move and rename files to `/media/shows` after processing
- Store configuration in `./config`

View logs:
```bash
docker-compose logs -f
```

## Local Setup (Alternative)

1. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create `.env` file with your TVDB API key:
```env
TVDB_API_KEY=your_api_key_here
```

4. Run the application:
```bash
python -m showrenamer.main /path/to/monitor
```

## Command Line Arguments

### Required Arguments
- `paths`: Directories to monitor for new files

### Configuration Options
- `--api-key`: TVDB API key (optional if set in .env)
- `--config-dir`: Configuration directory (defaults to ~/.config/showrenamer)
- `--cache-ttl`: Cache duration in days (default: 7)
- `--shows-dir`: Add a shows directory to search for existing shows and move files to (can be used multiple times)

### Behavior Options
- `--interactive`: Enable interactive mode with confirmations

### Operation Modes (mutually exclusive)
- `--enable-changes`: Enable actual file changes (requires SHOWRENAMER_ENABLE_CHANGES=true)
- `--rename-only`: Only rename files in place, don't move them

## Environment Variables

### Required
- `TVDB_API_KEY`: Your TVDB API key

### Operation Modes

The application runs in dry-run mode by default, showing what changes would be made without actually making them. To enable actual file changes, you must:

1. Set the environment variable: `SHOWRENAMER_ENABLE_CHANGES=true`
2. Use the `--enable-changes` flag when running the application

Additional modes:
- `SHOWRENAMER_RENAME_ONLY`: Only rename files, don't move them (requires SHOWRENAMER_ENABLE_CHANGES=true)

### Timing Settings
- `SHOWRENAMER_RETRY_INTERVAL`: How long to wait before retrying failed files (default: 86400 seconds / 24 hours)
- `SHOWRENAMER_STABILITY_PERIOD`: How long to wait before processing new files (default: 300 seconds / 5 minutes)

## File Logging

The application maintains detailed logs of all file operations in the config directory under `logs/`:
- Text and JSON format logs for easy reading and parsing
- Records all rename and move operations with success/failure status
- Stores metadata like show name, season, episode number
- Logs error messages for troubleshooting
- Allows auditing of file changes and operation history

## Configuration Files

The application uses several configuration files stored in the config directory:
- `show_cache.json`: Cache for API responses
- `name_patterns.json`: Patterns for parsing filenames
- `series_mapping.json`: Manual series name mappings
- `show_directories.json`: Configured show directories
- `logs/`: Directory containing operation logs