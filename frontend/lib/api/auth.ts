import type { User } from "@/types";
import { jsonBody, request } from "./client";

export const authApi = {
  register: (value: { username: string; email: string; password: string }) => request<{ user: User; message: string }>("/auth/register", jsonBody(value)),
  login: (value: { email: string; password: string }) => request<{ user: User; message: string }>("/auth/login", jsonBody(value)),
  me: () => request<User>("/auth/me"),
  logout: () => request<{ success: boolean }>("/auth/logout", { method: "POST" }),
};
