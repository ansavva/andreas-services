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
  primary: 'bg-primary text-primary-text hover:bg-primary-hover active:bg-primary-active',
  secondary: 'bg-surface-alt text-ink hover:bg-line active:bg-line',
  danger: 'bg-danger text-ivory hover:bg-danger-hover active:bg-danger-hover',
  ghost: 'bg-transparent text-ink hover:bg-surface-alt active:bg-line',
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
