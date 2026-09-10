// `.field-label` — a label stacked over its control, which is how every Humbugg
// form is written.
//
// This wraps the design system's `Field` rather than replacing it: `Field.Root`
// is what supplies the control's id and the `aria-labelledby` association that
// `Input` and `Textarea` read out of context, so a bare `<Text>` + `<Input>`
// pair would lose the label association entirely on both platforms. Humbugg's
// own typography and 7px gap are applied on top.
import { Field as DsField } from '@ansavva/design-system';
import type { ReactNode } from 'react';
import { Text, View } from 'react-native';

import { scopedStyles, useTheme } from '../theme/styles';
import { fonts } from '../theme/theme';

export function FieldLabel({
  label,
  hint,
  help,
  invalid = false,
  children,
}: {
  label: ReactNode;
  /** Muted text shown inline after the label, e.g. "(optional)". */
  hint?: string;
  /** Muted text shown under the control. */
  help?: string;
  invalid?: boolean;
  children: ReactNode;
}) {
  const theme = useTheme();
  const { styles } = theme;
  const local = localStyles(theme);
  return (
    <DsField.Root invalid={invalid} style={styles.fieldLabel}>
      <DsField.Label>
        <Text style={styles.fieldLabelText}>
          {label}
          {hint ? <Text style={local.hint}> {hint}</Text> : null}
        </Text>
      </DsField.Label>
      {children}
      {help ? (
        <DsField.Description>
          <Text style={local.help}>{help}</Text>
        </DsField.Description>
      ) : null}
    </DsField.Root>
  );
}

/** The label/control gap applied to a plain stacked pair with no `Field` semantics. */
export function Stack({ gap = 20, children }: { gap?: number; children: ReactNode }) {
  return <View style={{ gap }}>{children}</View>;
}

/** Built once per scheme — see `scopedStyles`. */
const localStyles = scopedStyles((t) => ({
  hint: { color: t.brand.muted, fontFamily: fonts.body },
  help: { color: t.brand.muted, fontFamily: fonts.body, fontSize: 12, lineHeight: 16 },
}));
