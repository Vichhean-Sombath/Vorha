export type User = { id: number; username: string; email: string; created_at: string };
export type Sound = {
  id: number;
  source_platform: string;
  source_url: string;
  external_id: string | null;
  title: string | null;
  creator_name: string | null;
  creator_username: string | null;
  thumbnail_url: string | null;
  playback_url: string | null;
  playback_media_type?: "audio" | "video";
  duration_seconds: number | null;
  is_playable: boolean;
  created_at: string;
};
export type PlaylistItem = { sound: Sound; position: number; added_at: string };
export type Playlist = { id: number; name: string; description: string | null; created_at: string; updated_at: string; items: PlaylistItem[] };
export type HistoryItem = { sound: Sound; progress_seconds: number; completed: boolean; last_played_at: string };
