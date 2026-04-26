import { normalizeCardName } from "@/lib/decklist";

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function validateEmail(email: string) {
  const normalized = normalizeEmail(email);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
    throw new Error("A valid email is required.");
  }

  return normalized;
}

export function validatePassword(password: string) {
  if (password.trim().length < 8) {
    throw new Error("Password must be at least 8 characters.");
  }

  return password;
}

export function requireUuid(value: string | undefined, label: string) {
  if (!value?.trim()) {
    throw new Error(`${label} is required.`);
  }

  return value;
}

export function normalizeLookupNames(names: string[]): string[] {
  return names.map((name) => normalizeCardName(name)).filter(Boolean);
}

