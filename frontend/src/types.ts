export interface ConversionRequest {
  url: string;
  target_platform: 'soundcloud';
  start_index: number;
  batch_size: number;
}

export interface Track {
  original: {
    name: string;
    artists: string[];
    duration: string;
  };
  converted?: {
    title: string;
    user: {
      username: string;
    };
    url: string;
  };
  success: boolean;
  status: string;
  error?: string;
}

export interface PerformanceStats {
  scraper_init_time: string;
  soundcloud_init_time: string;
  playlist_fetch_time: string;
  avg_search_time: string;
  total_search_time: string;
  total_time: string;
  rate_limited: boolean;
  browser_stats?: any;
}

export interface ConversionResponse {
  success: boolean;
  message: string;
  success_count: number;
  failure_count: number;
  results?: any[];
  details: {
    converted_tracks: number;
    total_tracks: number;
    success_rate: number;
    tracks: Track[];
    current_batch: BatchInfo;
    processing_phase: string;
    detailed_status: string;
    last_action_time: string;
    performance_stats?: PerformanceStats;
  };
}

export interface SearchRequest {
  track_name: string;
  artist_name: string;
  blacklisted_urls: string[];
}

export interface Alternative {
  title: string;
  user: {
    username: string;
  };
  url: string;
}

export const BATCH_SIZES = [5, 10, 20, 50] as const;
export type BatchSize = typeof BATCH_SIZES[number];

export interface BatchInfo {
  start: number;
  end: number;
  end_index: number;
  has_more: boolean;
  current_batch?: number;
  total_batches?: number;
  estimated_completion_time?: string;
  rate_limited?: boolean;
}