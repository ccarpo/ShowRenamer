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

2. Create your environment file:
```bash
cp .env.example .env
```

3. Edit `.env` with your configuration:
```env
TVDB_API_KEY=your_api_key_here
TV_SHOWS_SOURCE=/path/to/your/tv/shows
TV_SHOWS_DEST=/path/to/your/renamed/shows
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
- `--cache-ttl`: Cache duration in days
- `--show-dir`: Add a show directory to search for existing shows (can be used multiple times)

### Behavior Options
- `--no-interactive`: Skip confirmations


### Operation Modes (mutually exclusive)
- `--dry-run`: Show what would happen without making any changes
- `--rename-only`: Only rename files in place, don't move them

## Environment Variables

### Required
- `TVDB_API_KEY`: Your TVDB API key

### Optional Paths
- `TV_SHOWS_SOURCE`: Source directory for TV shows (default: ./media/incoming)
- `TV_SHOWS_DEST`: Destination directory for renamed shows (default: ./media/shows)

### Operation Modes

The application runs in dry-run mode by default, showing what changes would be made without actually making them. To enable actual file changes, you must:

1. Set the environment variable: `SHOWRENAMER_ENABLE_CHANGES=true`
2. Use the `--enable-changes` flag when running the application

Additional modes:
- `SHOWRENAMER_RENAME_ONLY`: Only rename files, don't move them (requires SHOWRENAMER_ENABLE_CHANGES=true)

## Configuration Files

The application uses several configuration files stored in the config directory:
- `show_cache.json`: Cache for API responses
- `name_patterns.json`: Patterns for parsing filenames
- `series_mapping.json`: Manual series name mappings
- `show_directories.json`: Configured show directories