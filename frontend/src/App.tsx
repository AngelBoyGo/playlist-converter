import React, { useState } from 'react';
import { Music, Loader2, AlertCircle, RefreshCw, ThumbsDown } from 'lucide-react';
import { ConversionResponse, Track, BATCH_SIZES, BatchSize, Alternative } from './types';
import { convertPlaylist, searchAlternative } from './api';

interface TrackPlayerProps {
  track: Track;
}

const TrackPlayer: React.FC<TrackPlayerProps> = ({ track }) => {
  if (!track.success || !track.converted) return null;
  
  return (
    <div className="mt-4">
      <iframe 
        width="100%" 
        height="166" 
        scrolling="no" 
        frameBorder="no" 
        allow="autoplay"
        src={`https://w.soundcloud.com/player/?url=${track.converted.url}&color=%23ff5500&auto_play=false&hide_related=true&show_comments=false&show_user=true&show_reposts=false&show_teaser=false`}
      ></iframe>
    </div>
  );
};

function App() {
  const [url, setUrl] = useState('');
  const [batchSize, setBatchSize] = useState<BatchSize>(10);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ConversionResponse | null>(null);
  const [feedbackLoading, setFeedbackLoading] = useState<Record<number, boolean>>({});
  const [alternatives, setAlternatives] = useState<Record<number, Alternative[]>>({});

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setAlternatives({});

    try {
      const response = await convertPlaylist({
        url,
        target_platform: 'soundcloud',
        start_index: 0,
        batch_size: batchSize,
      });
      
      if (!response.success) {
        throw new Error(response.message || 'Conversion failed');
      }
      
      setResult(response);
    } catch (err) {
      console.error('Error during conversion:', err);
      let errorMessage = 'An unexpected error occurred';
      
      if (err instanceof Error) {
        errorMessage = err.message;
      }
      
      // Look for specific browser initialization errors
      if (errorMessage.includes('browser') || errorMessage.includes('ChromeDriver')) {
        errorMessage = 'Browser initialization failed. There may be a compatibility issue with ChromeDriver. Please try again later or contact support.';
      }
      
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const loadMoreTracks = async () => {
    if (!result) return;
    
    setIsLoadingMore(true);
    try {
      const nextBatch = await convertPlaylist({
        url,
        target_platform: 'soundcloud',
        start_index: result.details.current_batch.end,
        batch_size: batchSize,
      });
      
      setResult({
        ...nextBatch,
        details: {
          ...nextBatch.details,
          tracks: [...result.details.tracks, ...nextBatch.details.tracks],
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more tracks');
    } finally {
      setIsLoadingMore(false);
    }
  };

  const handleWrongMatch = async (track: Track, index: number) => {
    setFeedbackLoading(prev => ({ ...prev, [index]: true }));
    try {
      const trackAlternatives = await searchAlternative({
        track_name: track.original.name,
        artist_name: track.original.artists[0],
        blacklisted_urls: track.converted ? [track.converted.url] : [],
      });
      
      setAlternatives(prev => ({ ...prev, [index]: trackAlternatives }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to find alternatives');
    } finally {
      setFeedbackLoading(prev => ({ ...prev, [index]: false }));
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-indigo-50">
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-3xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <div className="inline-block p-3 bg-indigo-100 rounded-full mb-4">
              <Music className="w-8 h-8 text-indigo-600" />
            </div>
            <h1 className="text-4xl font-bold text-gray-900 mb-4">
              Playlist Converter
            </h1>
            <p className="text-lg text-gray-600">
              Convert your favorite playlists to SoundCloud with ease
            </p>
          </div>

          {/* Conversion Form */}
          <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-lg p-6 mb-8">
            <div className="mb-6">
              <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-2">
                Playlist URL
              </label>
              <input
                type="url"
                id="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Enter Spotify or Apple Music playlist URL"
                className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                required
              />
            </div>

            <div className="mb-6">
              <label htmlFor="batchSize" className="block text-sm font-medium text-gray-700 mb-2">
                Batch Size
              </label>
              <select
                id="batchSize"
                value={batchSize}
                onChange={(e) => setBatchSize(Number(e.target.value) as BatchSize)}
                className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              >
                {BATCH_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size} tracks per batch
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-indigo-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? (
                <span className="flex items-center justify-center">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" />
                  Converting...
                </span>
              ) : (
                'Convert Playlist'
              )}
            </button>
          </form>

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-8 rounded-lg">
              <div className="flex items-start">
                <AlertCircle className="w-5 h-5 text-red-400 mr-2 mt-0.5 flex-shrink-0" />
                <div>
                  <h3 className="text-red-800 font-medium mb-1">Error</h3>
                  <p className="text-red-700">{error}</p>
                  {error.includes('browser') && (
                    <div className="mt-2 pt-2 border-t border-red-200">
                      <p className="text-sm text-red-600">
                        The server is having trouble with the Chrome browser setup. This can happen due to:
                      </p>
                      <ul className="list-disc list-inside text-sm text-red-600 mt-1">
                        <li>Version compatibility issues</li>
                        <li>Server resource limitations</li>
                        <li>Temporary service disruptions</li>
                      </ul>
                      <p className="text-sm text-red-600 mt-2">
                        Please try again later or try with a smaller playlist.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Results */}
          {result && (
            <div className="bg-white rounded-xl shadow-lg p-6">
              <h2 className="text-xl font-semibold mb-4">Conversion Results</h2>
              
              {/* Progress Bar */}
              <div className="mb-8">
                <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-indigo-600 transition-all duration-500"
                    style={{ width: `${(result.details.converted_tracks / result.details.total_tracks) * 100}%` }}
                  ></div>
                </div>
                <div className="mt-2 text-sm text-gray-600">
                  {result.details.converted_tracks} of {result.details.total_tracks} tracks processed
                  ({Math.round(result.details.success_rate * 100)}% success rate)
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex justify-between p-4 bg-gray-50 rounded-lg">
                  <span className="text-gray-600">Success Rate</span>
                  <span className="font-medium">{(result.details.success_rate * 100).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between p-4 bg-gray-50 rounded-lg">
                  <span className="text-gray-600">Converted Tracks</span>
                  <span className="font-medium">{result.success_count} / {result.details.total_tracks}</span>
                </div>
                
                <div className="mt-6">
                  <h3 className="text-lg font-medium mb-4">Converted Tracks</h3>
                  <div className="space-y-6">
                    {result.details.tracks.map((track, index) => (
                      <div
                        key={index}
                        className={`p-6 rounded-lg ${
                          track.success ? 'bg-green-50' : 'bg-red-50'
                        }`}
                      >
                        <div className="flex justify-between items-start">
                          <div>
                            <p className="font-medium">{track.original.name}</p>
                            <p className="text-sm text-gray-600">{track.original.artists.join(', ')}</p>
                            <p className="text-xs text-gray-500 mt-1">Duration: {track.original.duration}</p>
                          </div>
                          {track.success && track.converted && (
                            <div className="flex items-center space-x-4">
                              <a
                                href={track.converted.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-indigo-600 hover:text-indigo-700 text-sm font-medium"
                              >
                                Open in SoundCloud
                              </a>
                              <button
                                onClick={() => handleWrongMatch(track, index)}
                                disabled={feedbackLoading[index]}
                                className="p-2 text-gray-500 hover:text-red-500 transition-colors"
                                title="Report wrong match"
                              >
                                <ThumbsDown className="w-4 h-4" />
                              </button>
                            </div>
                          )}
                        </div>
                        
                        {track.success && track.converted && (
                          <div className="mt-2">
                            <p className="text-sm text-gray-600">
                              Matched with: <span className="font-medium">{track.converted.title}</span>
                              <span className="text-gray-500"> by {track.converted.user.username}</span>
                            </p>
                            <TrackPlayer track={track} />
                          </div>
                        )}

                        {!track.success && track.error && (
                          <p className="text-sm text-red-600 mt-2">{track.error}</p>
                        )}

                        {/* Alternatives Section */}
                        {alternatives[index] && alternatives[index].length > 0 && (
                          <div className="mt-4 border-t border-gray-200 pt-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">Alternative Matches</h4>
                            <div className="space-y-3">
                              {alternatives[index].map((alt, altIndex) => (
                                <div key={altIndex} className="flex justify-between items-center bg-white p-3 rounded-lg shadow-sm">
                                  <div>
                                    <p className="text-sm font-medium">{alt.title}</p>
                                    <p className="text-xs text-gray-500">{alt.user.username}</p>
                                  </div>
                                  <a
                                    href={alt.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-indigo-600 hover:text-indigo-700 text-sm"
                                  >
                                    Preview
                                  </a>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {feedbackLoading[index] && (
                          <div className="mt-4 flex items-center justify-center">
                            <RefreshCw className="w-4 h-4 animate-spin text-gray-500" />
                            <span className="ml-2 text-sm text-gray-500">Finding alternatives...</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {result.details.current_batch.has_more && (
                  <button
                    onClick={loadMoreTracks}
                    disabled={isLoadingMore}
                    className="mt-6 w-full bg-gray-100 text-gray-700 py-3 px-4 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                  >
                    {isLoadingMore ? (
                      <>
                        <Loader2 className="w-5 h-5 animate-spin mr-2" />
                        Loading more...
                      </>
                    ) : (
                      'Load More Tracks'
                    )}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;