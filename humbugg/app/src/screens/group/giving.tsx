// FOR <recipient>: everything about the person you drew (#690).
//
// The one dark card on the page is the reveal — their name, how far the gift has got, their
// wishes with your private claims on them. Under it, in ordinary cards, what they told you about
// themselves and the stage buttons. The anonymous chat sits beside every tab. Nothing about YOU is
// on this page; that is the next tab. The old exchange page interleaved the two, and a card
// headed "Your gift" sat above one headed "Your gift from your giver", both about a gift.
import { Text, View } from 'react-native';

import { api } from '../../api/client';
import { GiftStagePanel, GiftSteps } from '../../components/gift-progress';
import { Card } from '../../components/shell';
import { RecipientWishList } from '../../components/wishlist';
import { useTheme } from '../../theme/styles';
import type { RecipientAssignment } from '../../types';
import { firstName, useGroup } from './context';

export default function GivingScreen() {
  const { styles } = useTheme();
  const { groupId, group, me, assignment, busy, claimAction } = useGroup();

  if (!me.is_participating) {
    return (
      <Card>
        <Text style={styles.eyebrow}>Sitting this one out</Text>
        <Text style={[styles.heading, { marginTop: 4 }]}>Nobody to give to</Text>
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          You are in this group without taking part in the draw, so there is no recipient here.
          Your organizer can put you back in.
        </Text>
      </Card>
    );
  }

  if (group.status !== 'drawn' || !assignment) {
    return (
      <Card>
        <Text style={styles.eyebrow}>Your recipient</Text>
        <Text style={[styles.heading, { marginTop: 4 }]}>
          {group.status === 'drawn' ? 'Your match is on its way' : 'The draw hasn’t happened yet'}
        </Text>
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          {group.status === 'drawn'
            ? 'The draw has run but your match has not reached you yet. Try again in a moment.'
            : 'When your organizer runs the draw, the person you are giving to appears here and this tab takes their name. Until then, fill in what you would love on the next tab so your own giver has something to go on.'}
        </Text>
      </Card>
    );
  }

  const name = firstName(assignment.display_name);
  return (
    <>
      <RecipientCard
        assignment={assignment}
        busy={busy}
        onClaim={(wishId, state, quantity) =>
          void claimAction((token) => api.setWishClaim(token, groupId, wishId, state, quantity))
        }
        onRelease={(wishId) => void claimAction((token) => api.releaseWishClaim(token, groupId, wishId))}
      />
      {/* Gift progress (#132), the giver's end. The stage comes back on the assignment — it is the
          caller's own status for that assignment — so it needs no fetch of its own. */}
      {assignment.gift ? (
        <GiftStagePanel
          gift={assignment.gift}
          busy={busy}
          onChange={(stage) => void claimAction((token) => api.setGiftStage(token, groupId, stage))}
        />
      ) : null}
      <RecipientDetails name={name} assignment={assignment} />
    </>
  );
}

/** The reveal: who, how far along, and what they asked for. */
function RecipientCard({
  assignment,
  busy,
  onClaim,
  onRelease,
}: {
  assignment: RecipientAssignment;
  busy: boolean;
  onClaim(wishId: string, state: Parameters<typeof api.setWishClaim>[3], quantity: number): void;
  onRelease(wishId: string): void;
}) {
  const { styles } = useTheme();
  const name = firstName(assignment.display_name);
  return (
    <View style={styles.assignmentCard}>
      <Text style={styles.assignmentLabel}>You’re giving to</Text>
      <Text style={[styles.displayLg, styles.assignmentHeading, { marginTop: 8 }]}>
        {assignment.display_name}
      </Text>
      <Text style={[styles.assignmentText, styles.assignmentSubtle, { marginTop: 8 }]}>
        Only you can see this. {name} doesn’t know it’s you.
      </Text>
      {assignment.gift ? (
        <View style={{ marginTop: 24 }}>
          <GiftSteps gift={assignment.gift} />
        </View>
      ) : null}
      <View style={{ marginTop: 28 }}>
        <Text style={styles.assignmentLabel}>{name}’s wishlist</Text>
        <View style={{ marginTop: 8 }}>
          <RecipientWishList wishes={assignment.wishes ?? []} busy={busy} onClaim={onClaim} onRelease={onRelease} />
        </View>
      </View>
    </View>
  );
}

/** What they wrote about themselves, and where to send it. */
function RecipientDetails({ name, assignment }: { name: string; assignment: RecipientAssignment }) {
  const { styles } = useTheme();
  const address = Object.values(assignment.address ?? {}).filter(Boolean).join(', ');
  return (
    <Card>
      <Text style={styles.eyebrow}>{name}’s details</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Sizes, likes, and where to send it</Text>
      <View style={{ marginTop: 20, gap: 18 }}>
        <Detail label="Likes, sizes and hobbies" value={assignment.wishlist || 'Nothing added.'} />
        <Detail label="Please avoid" value={assignment.avoidances || 'Nothing listed.'} />
        <Detail label="Delivery address" value={address || 'No address provided.'} />
      </View>
    </Card>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  const { styles } = useTheme();
  return (
    <View>
      <Text style={styles.eyebrow}>{label}</Text>
      <Text style={[styles.body, { marginTop: 6 }]}>{value}</Text>
    </View>
  );
}
