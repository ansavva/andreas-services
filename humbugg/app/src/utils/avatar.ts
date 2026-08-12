// Client-side avatar helpers: the initials fallback rendering and the upload constraints that mirror
// the backend's validation (so obvious problems are caught before a request is made).
//
// Ported from the web app unchanged except for `validateAvatarFile`, which took a DOM `File`. There
// is no `File` on a device, and the picker (`expo-image-picker`) hands back a plain asset descriptor,
// so the check now takes the two fields it actually reads. That makes the module genuinely
// platform-agnostic rather than DOM-shaped — the web app's `File` still satisfies it structurally.
// The `readFileAsDataUrl` helper is gone for the same reason: `FileReader` does not exist on native,
// and the picker returns base64 directly (see `pickAvatar` below).

export const AVATAR_MAX_BYTES = 3 * 1024 * 1024;
export const AVATAR_ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'] as const;

/**
 * Derives up to two uppercase initials from a display name, falling back to the first character of an
 * email, then to a neutral placeholder. Used whenever there is no uploaded photo.
 */
export function initials(name?: string | null, fallback?: string | null): string {
  const source = (name ?? '').trim();
  if (source) {
    const parts = source.split(/\s+/).filter(Boolean);
    const first = parts[0]?.[0] ?? '';
    const last = parts.length > 1 ? parts[parts.length - 1]![0] : '';
    const result = (first + last).toUpperCase();
    if (result) return result;
  }
  const email = (fallback ?? '').trim();
  if (email) return email[0]!.toUpperCase();
  return '?';
}

// Deep, saturated backgrounds that all pair with white text at accessible contrast (>= 4.5:1).
const PALETTE: ReadonlyArray<{ bg: string; fg: string }> = [
  { bg: '#1d5545', fg: '#fffdf8' },
  { bg: '#a15b2d', fg: '#fffdf8' },
  { bg: '#2f5d8a', fg: '#fffdf8' },
  { bg: '#7a3f8c', fg: '#fffdf8' },
  { bg: '#94303d', fg: '#fffdf8' },
  { bg: '#3d6b4a', fg: '#fffdf8' },
  { bg: '#5a4b8a', fg: '#fffdf8' },
  { bg: '#4a5568', fg: '#fffdf8' },
];

/**
 * Picks a stable background/foreground pair for a name, so the same person always gets the same
 * colored initials avatar across sessions and devices.
 */
export function avatarColor(seed?: string | null): { bg: string; fg: string } {
  const key = ((seed ?? '').trim() || '?');
  let hash = 0;
  for (let index = 0; index < key.length; index += 1) {
    hash = (hash * 31 + key.charCodeAt(index)) >>> 0;
  }
  return PALETTE[hash % PALETTE.length]!;
}

/** The two fields the size/type check reads. A DOM `File` satisfies this structurally. */
export interface PickedImage {
  /** MIME type, e.g. `image/png`. */
  type: string;
  /** Byte length of the encoded image. */
  size: number;
}

/**
 * Validates a chosen image against the same content-type and size limits the backend enforces.
 * Returns an error message to display, or null when the image is acceptable.
 */
export function validateAvatarFile(file: PickedImage): string | null {
  if (!AVATAR_ALLOWED_TYPES.includes(file.type as (typeof AVATAR_ALLOWED_TYPES)[number])) {
    return 'Choose a PNG, JPEG, or WebP image.';
  }
  if (file.size > AVATAR_MAX_BYTES) {
    return `The image must be ${Math.round(AVATAR_MAX_BYTES / (1024 * 1024))} MB or smaller.`;
  }
  return null;
}

/** Assembles the `data:` URL the upload endpoint expects from a base64 payload. */
export function toDataUrl(mimeType: string, base64: string): string {
  return `data:${mimeType};base64,${base64}`;
}
