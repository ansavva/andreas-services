// One place that turns "the user wants to choose a photo" into the data URL the
// upload endpoint takes, so neither screen has to know about the picker.
//
// `expo-image-picker` replaces the web app's hidden `<input type="file">` +
// `FileReader` pair. It works on all three targets — a system sheet on iOS and
// Android, a file input under the hood on web — and returns base64 directly,
// which is exactly the shape `PUT /me/avatar` wants.
import * as ImagePicker from 'expo-image-picker';

import { toDataUrl, validateAvatarFile } from './avatar';

export type AvatarPickResult =
  | { kind: 'cancelled' }
  | { kind: 'error'; message: string }
  | { kind: 'picked'; dataUrl: string };

/** Opens the photo library and returns a validated `data:` URL, or why it could not. */
export async function pickAvatar(): Promise<AvatarPickResult> {
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    base64: true,
    quality: 0.9,
    // The avatar renders in a circle at 80px at most, so a full-resolution
    // photo is megabytes of base64 for no visible gain — and would trip the
    // 3 MB ceiling the backend enforces.
    allowsEditing: true,
    aspect: [1, 1],
  });

  if (result.canceled) return { kind: 'cancelled' };

  const asset = result.assets[0];
  if (!asset?.base64) return { kind: 'error', message: 'Unable to read that photo.' };

  const mimeType = asset.mimeType ?? 'image/jpeg';
  // base64 encodes 3 bytes as 4 characters; the padding is at most 2 bytes out.
  const size = asset.fileSize ?? Math.floor((asset.base64.length * 3) / 4);
  const validationError = validateAvatarFile({ type: mimeType, size });
  if (validationError) return { kind: 'error', message: validationError };

  return { kind: 'picked', dataUrl: toDataUrl(mimeType, asset.base64) };
}
