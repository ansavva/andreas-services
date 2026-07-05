import type { Accordion as AccordionNamespace } from '@base-ui/react/accordion';

import * as React from 'react';
import { Accordion as BaseAccordion } from '@base-ui/react/accordion';

import { cn } from '../../lib/cn';
import { disabledStyles, focusRing } from '../../lib/styles';

function AccordionRoot({ className, ...props }: AccordionNamespace.Root.Props) {
  return <BaseAccordion.Root className={cn('flex flex-col', className)} {...props} />;
}
AccordionRoot.displayName = 'Accordion.Root';

const AccordionItem = React.forwardRef<HTMLDivElement, AccordionNamespace.Item.Props>(
  ({ className, ...props }, ref) => (
    <BaseAccordion.Item
      ref={ref}
      className={cn('border-b border-neutral-200', className)}
      {...props}
    />
  ),
);
AccordionItem.displayName = 'Accordion.Item';

const AccordionHeader = React.forwardRef<HTMLHeadingElement, AccordionNamespace.Header.Props>(
  ({ className, ...props }, ref) => (
    <BaseAccordion.Header ref={ref} className={cn('flex', className)} {...props} />
  ),
);
AccordionHeader.displayName = 'Accordion.Header';

const AccordionTrigger = React.forwardRef<HTMLElement, AccordionNamespace.Trigger.Props>(
  ({ className, ...props }, ref) => (
    <BaseAccordion.Trigger
      ref={ref}
      className={cn(
        'flex flex-1 items-center justify-between py-3 text-sm font-medium text-neutral-900',
        focusRing,
        disabledStyles,
        className,
      )}
      {...props}
    />
  ),
);
AccordionTrigger.displayName = 'Accordion.Trigger';

const AccordionPanel = React.forwardRef<HTMLDivElement, AccordionNamespace.Panel.Props>(
  ({ className, ...props }, ref) => (
    <BaseAccordion.Panel
      ref={ref}
      className={cn(
        'h-[var(--accordion-panel-height)] overflow-hidden text-sm text-neutral-700 transition-[height]',
        className,
      )}
      {...props}
    />
  ),
);
AccordionPanel.displayName = 'Accordion.Panel';

export const Accordion = {
  Root: AccordionRoot,
  Item: AccordionItem,
  Header: AccordionHeader,
  Trigger: AccordionTrigger,
  Panel: AccordionPanel,
};
