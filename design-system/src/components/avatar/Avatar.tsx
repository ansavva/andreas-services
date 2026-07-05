import type { Avatar as AvatarNamespace } from '@base-ui/react/avatar';

import * as React from 'react';
import { Avatar as BaseAvatar } from '@base-ui/react/avatar';

import { cn } from '../../lib/cn';

const AvatarRoot = React.forwardRef<HTMLSpanElement, AvatarNamespace.Root.Props>(
  ({ className, ...props }, ref) => (
    <BaseAvatar.Root
      ref={ref}
      className={cn(
        'flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface-alt',
        className,
      )}
      {...props}
    />
  ),
);
AvatarRoot.displayName = 'Avatar.Root';

const AvatarImage = React.forwardRef<HTMLImageElement, AvatarNamespace.Image.Props>(
  ({ className, ...props }, ref) => (
    <BaseAvatar.Image ref={ref} className={cn('size-full object-cover', className)} {...props} />
  ),
);
AvatarImage.displayName = 'Avatar.Image';

const AvatarFallback = React.forwardRef<HTMLSpanElement, AvatarNamespace.Fallback.Props>(
  ({ className, ...props }, ref) => (
    <BaseAvatar.Fallback
      ref={ref}
      className={cn('text-sm font-medium text-muted', className)}
      {...props}
    />
  ),
);
AvatarFallback.displayName = 'Avatar.Fallback';

export const Avatar = {
  Root: AvatarRoot,
  Image: AvatarImage,
  Fallback: AvatarFallback,
};
