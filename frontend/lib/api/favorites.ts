import type { Sound } from "@/types";
import { request } from "./client";

export const favoritesApi = {
  list: () => request<Sound[]>("/favorites"),
  add: (id: number) => request<void>(`/favorites/${id}`, { method: "POST" }),
  remove: (id: number) => request<void>(`/favorites/${id}`, { method: "DELETE" }),
};
