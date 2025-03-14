# Playlist Converter

A web application that converts playlists between different music streaming platforms (currently supporting Apple Music and Spotify to SoundCloud).

## Features

- Convert Apple Music playlists to SoundCloud
- Convert Spotify playlists to SoundCloud
- Interactive web interface
- Real-time conversion progress
- Track matching verification

## Local Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/playlist-converter.git
cd playlist-converter
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy `.env.example` to `.env` and configure your environment variables:
```bash
cp .env.example .env
```

5. Run the development server:
```bash
python start_server.py
```

## Deployment to Heroku

1. Install the [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)

2. Login to Heroku:
```bash
heroku login
```

3. Create a new Heroku app:
```bash
heroku create your-app-name
```

4. Add the Chrome buildpack:
```bash
heroku buildpacks:add https://github.com/heroku/heroku-buildpack-google-chrome
heroku buildpacks:add https://github.com/heroku/heroku-buildpack-chromedriver
heroku buildpacks:add heroku/python
```

5. Configure environment variables:
```bash
heroku config:set CHROME_BINARY_LOCATION=/app/.apt/usr/bin/google-chrome
heroku config:set ENVIRONMENT=production
```

6. Deploy the application:
```bash
git push heroku main
```

7. Open the application:
```bash
heroku open
```

## Production Considerations

- Set up monitoring and error tracking (e.g., Sentry)
- Configure rate limiting
- Add SSL certificate
- Set up a custom domain
- Monitor server resources

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 