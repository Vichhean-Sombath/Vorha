import type { HistoryItem } from "@/types";
import { request } from "./client";

export const historyApi = {
  list: () => request<HistoryItem[]>("/history"),
  record: (sound_id: number, progress_seconds = 0, completed = false) => request<HistoryItem>("/history", { method: "POST", body: JSON.stringify({ sound_id, progress_seconds, completed }) }),
  clear: () => request<void>("/history", { method: "DELETE" }),
};
