// The socket client (#691): a ticket per connect, a nudge per message, backoff on a close, and a
// clean stop. A fake socket stands in for the browser's; fake timers drive the backoff.
import { RealtimeClient, type RealtimeNudge, type SocketLike } from './client';

class FakeSocket implements SocketLike {
  static opened: FakeSocket[] = [];
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) { FakeSocket.opened.push(this); }
  send(data: string) { this.sent.push(data); }
  close() { this.closed = true; this.readyState = 3; }
  open() { this.readyState = 1; this.onopen?.({}); }
  receive(data: unknown) { this.onmessage?.({ data }); }
  drop() { this.readyState = 3; this.onclose?.({}); }
}

function client(overrides: Partial<ConstructorParameters<typeof RealtimeClient>[0]> = {}) {
  let n = 0;
  const tickets = jest.fn(async () => `ticket-${++n}`);
  const instance = new RealtimeClient({
    url: 'ws://example.test/ws',
    ticket: tickets,
    open: (url) => new FakeSocket(url),
    minDelay: 1_000,
    maxDelay: 8_000,
    pingEvery: 60_000,
    random: () => 1,
    ...overrides,
  });
  return { instance, tickets };
}

const flush = () => new Promise<void>((resolve) => { setImmediate(resolve); });

beforeEach(() => {
  FakeSocket.opened = [];
  // setImmediate stays real: it is how a test lets the client's awaits settle.
  jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
});
afterEach(() => jest.useRealTimers());

it('connects with a fresh ticket in the query string, and reports the connection', async () => {
  const { instance, tickets } = client();
  const status: boolean[] = [];
  instance.onStatus((next) => status.push(next));

  instance.start();
  await flush();

  expect(tickets).toHaveBeenCalledTimes(1);
  expect(FakeSocket.opened[0]!.url).toBe('ws://example.test/ws?ticket=ticket-1');
  FakeSocket.opened[0]!.open();
  expect(instance.connected).toBe(true);
  expect(status).toEqual([true]);
});

it('hands a well-formed nudge to every subscriber and drops anything else', async () => {
  const { instance } = client();
  const seen: RealtimeNudge[] = [];
  instance.subscribe((nudge) => seen.push(nudge));
  instance.start();
  await flush();
  const socket = FakeSocket.opened[0]!;
  socket.open();

  socket.receive(JSON.stringify({ type: 'questions', group_id: 'g1', side: 'recipient' }));
  socket.receive('not json');
  socket.receive(JSON.stringify({ type: 'questions', group_id: 'g1', side: 'someone' }));
  socket.receive(JSON.stringify({ type: 'questions', group_id: 'g1', side: 'giver', body: 'leak?' }));

  expect(seen).toEqual([
    { type: 'questions', group_id: 'g1', side: 'recipient' },
    { type: 'questions', group_id: 'g1', side: 'giver' },
  ]);
});

it('reconnects after a close with growing delays and a new ticket each time', async () => {
  const { instance, tickets } = client();
  instance.start();
  await flush();
  FakeSocket.opened[0]!.open();

  FakeSocket.opened[0]!.drop();
  expect(instance.connected).toBe(false);
  // random() is 1, so each delay is the full ceiling: 1 s, then 2 s.
  jest.advanceTimersByTime(999);
  await flush();
  expect(FakeSocket.opened).toHaveLength(1);
  jest.advanceTimersByTime(1);
  await flush();
  expect(FakeSocket.opened).toHaveLength(2);
  expect(FakeSocket.opened[1]!.url).toContain('ticket=ticket-2');

  FakeSocket.opened[1]!.drop();
  jest.advanceTimersByTime(1_999);
  await flush();
  expect(FakeSocket.opened).toHaveLength(2);
  jest.advanceTimersByTime(1);
  await flush();
  expect(FakeSocket.opened).toHaveLength(3);
  expect(tickets).toHaveBeenCalledTimes(3);
});

it('keeps trying when the ticket cannot be minted', async () => {
  const ticket = jest.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue('t2');
  const { instance } = client({ ticket });
  instance.start();
  await flush();
  expect(FakeSocket.opened).toHaveLength(0);

  jest.advanceTimersByTime(1_000);
  await flush();
  expect(FakeSocket.opened).toHaveLength(1);
});

it('pings an open socket so the gateway keeps it', async () => {
  const { instance } = client();
  instance.start();
  await flush();
  const socket = FakeSocket.opened[0]!;
  socket.open();

  jest.advanceTimersByTime(60_000);

  expect(socket.sent).toEqual([JSON.stringify({ action: 'ping' })]);
});

it('stops cleanly: closes the socket and never reconnects', async () => {
  const { instance } = client();
  instance.start();
  await flush();
  const socket = FakeSocket.opened[0]!;
  socket.open();

  instance.stop();

  expect(socket.closed).toBe(true);
  expect(instance.connected).toBe(false);
  jest.advanceTimersByTime(60_000);
  await flush();
  expect(FakeSocket.opened).toHaveLength(1);
});
