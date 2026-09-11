// Managed invitations (#574) — the organizer sends the invitations instead of pasting a link.
//
// The Free way to invite somebody is to copy one link and send it yourself, which works and scales
// to six. This is the Plus way: addresses go in, Humbugg sends and tracks each one, and the
// organizer can see which have bounced or gone unanswered rather than guessing from who has not
// turned up.
//
// The backend has been able to do this since August 2026 and no screen called it. That is the whole
// defect this file closes, so it deliberately covers every endpoint that exists — create, resend
// and revoke — rather than the one that is easiest to render.
//
// The panel itself moved into `people.tsx` (#682): an invitation is a future member, and its row
// belongs in the one list of people with the members' rows, not in a card of its own. What is left
// here is the piece that is not about rendering.

/**
 * Split whatever was pasted into addresses.
 *
 * People paste from a mail client, a spreadsheet column or a chat message, so the separator is
 * whichever of comma, semicolon, newline or space happens to be there. Validation is the server's —
 * it owns the rule and names the offending address in its error, and a second regex here would only
 * be a different opinion about what an address is.
 */
export function splitAddresses(raw: string): string[] {
  const seen = new Set<string>();
  return raw
    .split(/[,;\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .filter((part) => {
      const key = part.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}
