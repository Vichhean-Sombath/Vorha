import type { Sound } from "@/types";
import { jsonBody, request } from "./client";

export const soundsApi = {
  analyze: (url: string) => request<Sound>("/sounds/analyze", jsonBody({ url })),
  prepareAudio: (soundId: number) => request<Sound>(`/sounds/${soundId}/audio`, { method: "POST" }),
  list: (q = "", page = 1) => request<{ items: Sound[]; page: number; limit: number; total: number }>(`/sounds?q=${encodeURIComponent(q)}&page=${page}`),
};
