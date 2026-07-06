// Low-level re-exports from @base-ui/react for advanced composition —
// unstyled, since there's nothing visual about any of these.
export { DirectionProvider, useDirection } from '@base-ui/react/direction-provider';
export { CSPProvider } from '@base-ui/react/csp-provider';
export {
  makeEventPreventable,
  mergeClassNames,
  mergeProps,
  mergePropsN,
} from '@base-ui/react/merge-props';
export { useRender } from '@base-ui/react/use-render';
export { useMediaQuery } from '@base-ui/react/unstable-use-media-query';
