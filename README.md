# Playlist Converter

Convert playlists between music streaming platforms (Spotify, Apple Music, SoundCloud).

## Features

- Extract tracks from Spotify and Apple Music playlists
- Find matching tracks on SoundCloud
- Preview tracks with SoundCloud embedded player
- Batch processing for large playlists
- Wrong match reporting with alternatives
- Detailed progress tracking

## Tech Stack

- **Backend**: Python 3.9, FastAPI, Selenium
- **Frontend**: React, TypeScript, Tailwind CSS
- **Deployment**: Docker, Render

## Local Development

### Prerequisites

- Python 3.9+
- Node.js 16+
- Chrome/Chromium browser

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/playlist-converter.git
cd playlist-converter

# Install dependencies
pip install -r requirements.txt

# Start the backend server
python start_server.py
```

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Access the Application

Open your browser and navigate to http://localhost:8080

## Deployment

This application is configured for easy deployment on Render:

1. Fork this repository
2. Connect your Render account to GitHub
3. Create a new Web Service in Render
4. Select this repository
5. Choose "Docker" as the environment
6. Choose the free instance type
7. Click "Create Web Service"

## Usage

1. Enter a Spotify or Apple Music playlist URL
2. Select batch size (5, 10, 20, or 50 tracks)
3. Click "Convert Playlist"
4. Browse and preview the converted tracks
5. Use "Wrong Match" for incorrect matches
6. Enjoy your converted playlist on SoundCloud!

## License

MIT 