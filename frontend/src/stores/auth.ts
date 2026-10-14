import { create } from "zustand";

interface AuthState {
  /** Access token JWT: vive solo en memoria, nunca en localStorage. */
  accessToken: string | null;
  setAccessToken: (token: string | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  setAccessToken: (accessToken) => set({ accessToken }),
}));
