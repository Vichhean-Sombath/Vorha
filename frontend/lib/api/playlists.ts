import type { Playlist } from "@/types";
import { jsonBody, request } from "./client";

export const playlistsApi = {
  list: () => request<Playlist[]>("/playlists"),
  create: (name: string, description?: string) => request<Playlist>("/playlists", jsonBody({ name, description })),
  update: (id: number, patch: { name?: string; cover_image?: string | null }) => request<Playlist>(`/playlists/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  rename: (id: number, name: string) => request<Playlist>(`/playlists/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  remove: (id: number) => request<void>(`/playlists/${id}`, { method: "DELETE" }),
  addSound: (id: number, sound_id: number) => request<Playlist>(`/playlists/${id}/sounds`, jsonBody({ sound_id })),
  removeSound: (id: number, soundId: number) => request<void>(`/playlists/${id}/sounds/${soundId}`, { method: "DELETE" }),
  reorder: (id: number, sound_ids: number[]) => request<Playlist>(`/playlists/${id}/reorder`, { method: "PATCH", body: JSON.stringify({ sound_ids }) }),
};
