"use client";

const TOKEN_STORAGE_KEY = "magicview.auth.token";

let memoryToken: string | null = null;

function hasWindow() {
  return typeof window !== "undefined";
}

export function getStoredAuthToken(): string | null {
  if (!hasWindow()) return null;

  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

export function setStoredAuthToken(token: string) {
  memoryToken = token;
  if (!hasWindow()) return;

  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // In-app browsers / private modes can block storage. Memory fallback is enough for MVP.
  }
}

export function clearStoredAuthToken() {
  memoryToken = null;
  if (!hasWindow()) return;

  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Ignore storage errors.
  }
}
