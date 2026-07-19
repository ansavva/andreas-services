import { avatarColor, initials } from '../utils/avatar';

interface AvatarProps {
  /** Uploaded photo URL. When present it is shown; otherwise a colored initials circle renders. */
  src?: string | null;
  name?: string | null;
  email?: string | null;
  size?: number;
  className?: string;
}

/**
 * Renders a user's avatar: the uploaded photo when one exists, otherwise a deterministic colored
 * circle with their initials. Decorative by default (`aria-hidden`) — the surrounding control supplies
 * the accessible label.
 */
export function Avatar({ src, name, email, size = 36, className = '' }: AvatarProps) {
  const dimension = `${size}px`;
  if (src) {
    return (
      <img
        src={src}
        alt=""
        aria-hidden="true"
        width={size}
        height={size}
        style={{ width: dimension, height: dimension }}
        className={`rounded-full object-cover ${className}`}
      />
    );
  }
  const { bg, fg } = avatarColor(name || email);
  return (
    <span
      aria-hidden="true"
      style={{ width: dimension, height: dimension, backgroundColor: bg, color: fg, fontSize: size * 0.4 }}
      className={`inline-flex select-none items-center justify-center rounded-full font-heading font-bold leading-none ${className}`}
    >
      {initials(name, email)}
    </span>
  );
}
