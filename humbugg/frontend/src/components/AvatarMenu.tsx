import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router';

import { useAuth } from '../context/AuthContext';
import { useProfile } from '../context/ProfileContext';
import { Avatar } from './Avatar';

interface MenuItem {
  label: string;
  onSelect(): void;
  danger?: boolean;
}

/**
 * Top-right account menu. The trigger shows the user's photo (or initials fallback) and opens a menu
 * with Settings, My groups, and Sign out. Fully keyboard operable: Enter/Space/ArrowDown open and focus
 * the first item, arrows/Home/End move a roving focus, Escape returns focus to the trigger, and an
 * outside click or Tab closes it. Semantics follow the WAI-ARIA menu-button pattern.
 */
export function AvatarMenu() {
  const auth = useAuth();
  const { profile } = useProfile();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();

  const displayName = profile?.display_name ?? auth.email ?? 'Your account';

  const items: MenuItem[] = [
    { label: 'Settings', onSelect: () => navigate('/app/settings') },
    { label: 'My groups', onSelect: () => navigate('/app') },
    { label: 'Sign out', onSelect: () => void auth.logout().then(() => navigate('/')), danger: true },
  ];

  useEffect(() => {
    if (!open) return undefined;
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  function openMenu(focusIndex: number) {
    setOpen(true);
    // Focus after the menu paints so the item refs exist.
    requestAnimationFrame(() => itemRefs.current[focusIndex]?.focus());
  }

  function closeMenu(returnFocus = true) {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  }

  function onButtonKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openMenu(0);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      openMenu(items.length - 1);
    }
  }

  function onItemKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        itemRefs.current[(index + 1) % items.length]?.focus();
        break;
      case 'ArrowUp':
        event.preventDefault();
        itemRefs.current[(index - 1 + items.length) % items.length]?.focus();
        break;
      case 'Home':
        event.preventDefault();
        itemRefs.current[0]?.focus();
        break;
      case 'End':
        event.preventDefault();
        itemRefs.current[items.length - 1]?.focus();
        break;
      case 'Escape':
        event.preventDefault();
        closeMenu();
        break;
      case 'Tab':
        setOpen(false);
        break;
      default:
        break;
    }
  }

  function select(item: MenuItem) {
    closeMenu(false);
    item.onSelect();
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => (open ? closeMenu(false) : setOpen(true))}
        onKeyDown={onButtonKeyDown}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Account menu for ${displayName}`}
        className="flex items-center gap-2 rounded-full border border-line/80 bg-card p-1 pr-2 transition hover:border-line focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
      >
        <Avatar src={profile?.avatar_url} name={profile?.display_name} email={auth.email} size={32} />
        <span className="hidden max-w-[10rem] truncate font-body text-sm font-medium text-ink sm:inline">{displayName}</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 text-muted" fill="currentColor">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z" clipRule="evenodd" />
        </svg>
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Account"
          className="absolute right-0 z-20 mt-2 w-52 overflow-hidden rounded-xl border border-line bg-card p-1 shadow-lg"
        >
          {items.map((item, index) => (
            <button
              key={item.label}
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              type="button"
              role="menuitem"
              tabIndex={-1}
              onClick={() => select(item)}
              onKeyDown={(event) => onItemKeyDown(event, index)}
              className={`block w-full rounded-lg px-3 py-2 text-left font-body text-sm font-medium transition focus:outline-none ${
                item.danger
                  ? 'text-danger hover:bg-danger/10 focus-visible:bg-danger/10'
                  : 'text-ink hover:bg-surface-alt focus-visible:bg-surface-alt'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
