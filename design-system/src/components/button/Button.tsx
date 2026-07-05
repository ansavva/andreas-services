import type { Button as ButtonNamespace } from '@base-ui/react/button';

import * as React from 'react';
import { Button as BaseButton } from '@base-ui/react/button';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

export type ButtonIntent = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends Omit<ButtonNamespace.Props, 'className'> {
  intent?: ButtonIntent;
  size?: ButtonSize;
  className?: string;
}

const intentStyles: Record<ButtonIntent, string> = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800',
  secondary: 'bg-neutral-100 text-neutral-900 hover:bg-neutral-200 active:bg-neutral-300',
  danger: 'bg-danger-600 text-white hover:bg-danger-700 active:bg-danger-700',
  ghost: 'bg-transparent text-neutral-900 hover:bg-neutral-100 active:bg-neutral-200',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'h-8 gap-1.5 px-3 text-sm',
  md: 'h-10 gap-2 px-4 text-sm',
  lg: 'h-12 gap-2 px-6 text-base',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, intent = 'primary', size = 'md', ...props }, ref) => {
    return (
      <BaseButton
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-md font-medium transition-colors',
          focusRing,
          disabledStyles,
          intentStyles[intent],
          sizeStyles[size],
          className,
        )}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';
