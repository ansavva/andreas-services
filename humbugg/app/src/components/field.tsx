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
import { StyleSheet, Text, View } from 'react-native';

import { styles } from '../theme/styles';
import { brand, fonts } from '../theme/theme';

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

const local = StyleSheet.create({
  hint: { color: brand.muted, fontFamily: fonts.body },
  help: { color: brand.muted, fontFamily: fonts.body, fontSize: 12, lineHeight: 16 },
});
