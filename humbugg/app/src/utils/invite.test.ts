// The invite secret rides in the URL fragment. This is the one piece of routing
// behaviour that no framework carries for us, so it gets its own test: an
// already-sent invitation link that stops working is not a recoverable failure.
import { inviteFromUrl } from './invite';

describe('inviteFromUrl', () => {
  it('reads the secret out of a full invitation URL', () => {
    expect(inviteFromUrl('https://app.humbugg.com/join/abc#invite=s3cr3t')).toBe('s3cr3t');
  });

  it('reads it from a bare fragment, which is what a browser exposes', () => {
    expect(inviteFromUrl('#invite=s3cr3t')).toBe('s3cr3t');
  });

  it('reads it from a native deep link', () => {
    expect(inviteFromUrl('humbugg://join/abc#invite=s3cr3t')).toBe('s3cr3t');
  });

  it('survives other fragment parameters alongside it', () => {
    expect(inviteFromUrl('/join/abc#foo=1&invite=s3cr3t&bar=2')).toBe('s3cr3t');
  });

  it('is null when the link carries no fragment at all', () => {
    expect(inviteFromUrl('https://app.humbugg.com/join/abc')).toBeNull();
  });

  it('is null when the fragment carries no invite', () => {
    expect(inviteFromUrl('https://app.humbugg.com/join/abc#other=1')).toBeNull();
  });

  it('tolerates a missing URL', () => {
    expect(inviteFromUrl(null)).toBeNull();
    expect(inviteFromUrl(undefined)).toBeNull();
  });
});
