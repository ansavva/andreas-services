// What stands in for a picture nobody uploaded, and what a picked file has to
// be before it is sent. Ported from humbugg's `utils/avatar.ts`, minus the
// per-person colour: studio is one muted tint, and a rainbow of initials in a
// dark sidebar was the look it left behind.

/** The largest picture the API accepts, and the three types a browser makes. */
export const AVATAR_MAX_BYTES = 3 * 1024 * 1024;
export const AVATAR_ALLOWED_TYPES = ["image/png", "image/jpeg", "image/webp"] as const;

/**
 * Up to two uppercase initials from a display name, then the first character
 * of the address, then a neutral mark. Drawn wherever there is no picture.
 */
export function initials(name?: string | null, fallback?: string | null): string {
  const source = (name ?? "").trim();
  if (source) {
    const parts = source.split(/\s+/).filter(Boolean);
    const first = parts[0]?.[0] ?? "";
    const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
    const result = (first + last).toUpperCase();
    if (result) return result;
  }
  const email = (fallback ?? "").trim();
  if (email) return email[0]!.toUpperCase();
  return "?";
}

/**
 * The size and type check the API also makes, so the obvious mistakes are
 * caught before four megabytes of base64 leave the tab. Returns the sentence
 * to show, or `null` when the file is fine.
 */
export function validateAvatarFile(file: { type: string; size: number }): string | null {
  if (!AVATAR_ALLOWED_TYPES.includes(file.type as (typeof AVATAR_ALLOWED_TYPES)[number])) {
    return "Choose a PNG, JPEG or WebP image.";
  }
  if (file.size > AVATAR_MAX_BYTES) {
    return `The image must be ${Math.round(AVATAR_MAX_BYTES / (1024 * 1024))} MB or smaller.`;
  }
  return null;
}

/** A `File` as the data URL `POST /api/account/avatar` takes. */
export function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Could not read the file."));
    reader.onload = () => resolve(reader.result as string);
    reader.readAsDataURL(file);
  });
}
