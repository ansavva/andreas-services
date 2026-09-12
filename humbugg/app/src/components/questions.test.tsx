// Anonymous questions (#131), on the app side.
//
// The API sends a SIDE and never a person, so the app has no identity to leak — unless it invents
// one. These tests pin that it does not: the same thread rendered from both seats names the other
// side by its role, names the viewer "You" to a screen reader and nothing else, and never anything
// more. The rest pins what makes it a chat: Enter sends, the thread refreshes on its own, and
// nothing about a message count closes the composer.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Platform } from 'react-native';

import type { QuestionThread } from '../types';

const mocks = {
  getGiverQuestions: jest.fn(),
  getRecipientQuestions: jest.fn(),
  askQuestion: jest.fn(),
  replyToQuestion: jest.fn(),
  setQuestionsBlocked: jest.fn(),
  markQuestionsSeen: jest.fn(),
};

jest.mock('../api/client', () => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, _code: string, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    api: {
      getGiverQuestions: (...args: unknown[]) => mocks.getGiverQuestions(...args),
      getRecipientQuestions: (...args: unknown[]) => mocks.getRecipientQuestions(...args),
      askQuestion: (...args: unknown[]) => mocks.askQuestion(...args),
      replyToQuestion: (...args: unknown[]) => mocks.replyToQuestion(...args),
      setQuestionsBlocked: (...args: unknown[]) => mocks.setQuestionsBlocked(...args),
      markQuestionsSeen: (...args: unknown[]) => mocks.markQuestionsSeen(...args),
    },
    ApiError,
  };
});

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({ accessToken: () => Promise.resolve('token'), authenticated: true }),
}));

jest.mock('../context/profile-context', () => ({
  useProfile: () => ({ profile: { display_name: 'Priya Test', avatar_url: null } }),
}));

jest.mock('./shell', () => {
  const { View } = require('react-native');
  return { Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View> };
});

import { ChatPanel } from './questions';

const { ApiError } = jest.requireMock('../api/client') as {
  ApiError: new (status: number, code: string, message: string) => Error;
};

/** The panel opens on the giver's conversation; the recipient's is a switch away. */
async function openRecipient() {
  render(<ChatPanel groupId="g1" />);
  await waitFor(() => expect(screen.getAllByText('Your Secret Santa')[0]).toBeTruthy());
  await act(async () => {
    fireEvent.press(screen.getAllByText('Your Secret Santa')[0]!);
  });
}

/** The exact payload both sides receive — identical, which is the server's guarantee. */
const THREAD: QuestionThread = {
  messages: [
    { message_id: 'm1', author: 'giver', body: 'What size do you take?', created_at: 'now' },
    { message_id: 'm2', author: 'recipient', body: 'Medium, thanks.', created_at: 'now' },
  ],
  blocked: false,
  can_send: true,
  blocked_reason: null,
  unread: 0,
};

beforeEach(() => {
  jest.clearAllMocks();
  mocks.getGiverQuestions.mockResolvedValue(THREAD);
  mocks.getRecipientQuestions.mockResolvedValue(THREAD);
  mocks.markQuestionsSeen.mockResolvedValue(THREAD);
});

describe('the thread', () => {
  it('names the reply by role and never labels the giver’s own bubble', async () => {
    render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(screen.getByText('What size do you take?')).toBeTruthy());
    // The who-row and the caption; nothing else.
    expect(screen.getAllByText('Them')).toHaveLength(2);
    // A chat does not caption your own bubbles. "You" reaches a screen reader only, below.
    expect(screen.queryByText('You')).toBeNull();
  });

  /**
   * The same payload from the other seat. The roles simply swap — the recipient is told
   * "Your Secret Santa", which is a role, and there is no branch anywhere that could produce a name.
   */
  it('renders the same thread from the recipient’s seat without naming anyone', async () => {
    await openRecipient();

    await waitFor(() => expect(screen.getByText('Medium, thanks.')).toBeTruthy());
    // The tab and the caption both say it; neither says a name.
    expect(screen.getAllByText('Your Secret Santa').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('Them')).toBeNull();
    // The explanation is in the tab's own accessible name — read without hovering — and shows on
    // hover or focus. Neither claims to know who asked.
    expect(screen.queryByText(/Humbugg does not tell you who/)).toBeNull();
    const tab = screen.getByLabelText(/Your Secret Santa\. Someone giving you a gift/);
    await act(async () => {
      fireEvent(tab, 'hoverIn');
    });
    expect(screen.getByText(/Humbugg does not tell you who/)).toBeTruthy();
    await act(async () => {
      fireEvent(tab, 'hoverOut');
    });
    expect(screen.queryByText(/Humbugg does not tell you who/)).toBeNull();
  });

  it('gives a screen reader one sentence per message, with the viewer as "You"', async () => {
    await openRecipient();

    await waitFor(() =>
      expect(screen.getByLabelText('Your Secret Santa: What size do you take?')).toBeTruthy());
    expect(screen.getByLabelText('You: Medium, thanks.')).toBeTruthy();
  });

  /**
   * The other side's role appears once per run, not on every bubble — three questions in a row
   * are one caption, the way a chat captions a run of messages from one person.
   */
  it('captions a run of messages from the other side once', async () => {
    mocks.getRecipientQuestions.mockResolvedValue({
      ...THREAD,
      messages: [
        { message_id: 'm1', author: 'giver', body: 'Size?', created_at: 'now' },
        { message_id: 'm2', author: 'giver', body: 'Colour?', created_at: 'now' },
        { message_id: 'm3', author: 'giver', body: 'Already own it?', created_at: 'now' },
      ],
    });
    await openRecipient();

    await waitFor(() => expect(screen.getByText('Already own it?')).toBeTruthy());
    // One tab, the who-row, one caption — not one caption per bubble.
    expect(screen.getAllByText('Your Secret Santa')).toHaveLength(3);
  });

  it('marks the day where the date turns, and never for a timestamp it cannot read', async () => {
    const today = new Date();
    const lastYear = new Date(today.getFullYear() - 1, 5, 14, 9, 30);
    mocks.getGiverQuestions.mockResolvedValue({
      ...THREAD,
      messages: [
        { message_id: 'm1', author: 'giver', body: 'Old', created_at: lastYear.toISOString() },
        { message_id: 'm2', author: 'recipient', body: 'New', created_at: today.toISOString() },
        { message_id: 'm3', author: 'giver', body: 'Unknown', created_at: 'now' },
      ],
    });
    render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(screen.getByText('Today')).toBeTruthy());
    expect(screen.getByText(new RegExp(`Jun.*${lastYear.getFullYear()}`))).toBeTruthy();
    expect(screen.getAllByText(/^(Today|Yesterday|.*\d{4})$/)).toHaveLength(2);
  });
});

/**
 * Who the tabs are named for. The giver's conversation is with a person they know — their own
 * recipient, the name on their assignment card — and takes that name. The recipient's is with
 * someone they must not know, and takes the role. There is no prop through which it could take a
 * name; `recipientName` reaches one tab and one caption, and the test pins which.
 */
describe('naming the other end', () => {
  it('names the giver’s conversation after their recipient, and the other after the role', async () => {
    render(<ChatPanel groupId="g1" recipient={{ name: 'Tariq Test' }} />);

    // The tab, the who-row and the caption all carry the recipient; the other tab carries the role.
    await waitFor(() => expect(screen.getAllByText('Tariq Test')).toHaveLength(3));
    expect(screen.getByText('Your Secret Santa')).toBeTruthy();
    expect(screen.queryByText('About their gift')).toBeNull();
  });

  it('captions the recipient’s bubbles with their name on the giver’s side only', async () => {
    render(<ChatPanel groupId="g1" recipient={{ name: 'Tariq Test' }} />);
    await waitFor(() => expect(screen.getByLabelText('Tariq Test: Medium, thanks.')).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getAllByText('Your Secret Santa')[0]!);
    });
    // Same payload, other seat: the giver's line is captioned by role, and Tariq is nowhere in it.
    await waitFor(() => expect(screen.getByLabelText('Your Secret Santa: What size do you take?')).toBeTruthy());
    expect(screen.queryByLabelText(/Tariq Test:/)).toBeNull();
  });
});

/**
 * Unread. The count comes from the server and shows on the tab that is not open; opening a
 * conversation is what clears it — the panel says so explicitly, because fetching (the poll) is
 * not seeing.
 */
describe('unread', () => {
  it('shows the count on the other conversation and clears it when opened', async () => {
    mocks.getRecipientQuestions.mockResolvedValue({ ...THREAD, unread: 2 });
    render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(screen.getByText('Your Secret Santa · 2')).toBeTruthy());
    // Not on screen yet, so not seen.
    expect(mocks.markQuestionsSeen).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.press(screen.getByText('Your Secret Santa · 2'));
    });
    await waitFor(() => expect(mocks.markQuestionsSeen).toHaveBeenCalledWith('token', 'g1', 'recipient'));
    await waitFor(() => expect(screen.queryByText('Your Secret Santa · 2')).toBeNull());
  });

  it('marks the open conversation seen as soon as it loads with unread messages', async () => {
    mocks.getGiverQuestions.mockResolvedValue({ ...THREAD, unread: 1 });
    render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(mocks.markQuestionsSeen).toHaveBeenCalledWith('token', 'g1', 'giver'));
    expect(mocks.markQuestionsSeen).not.toHaveBeenCalledWith('token', 'g1', 'recipient');
  });
});

/**
 * The rail folds away to a launcher and the choice is remembered. Folded, the threads keep
 * polling so the launcher can carry the total unread — and nothing is marked seen, because
 * nothing is on screen.
 */
describe('the rail', () => {
  it('closes to a launcher carrying the unread total, and opens again', async () => {
    mocks.getGiverQuestions.mockResolvedValue({ ...THREAD, unread: 1 });
    mocks.getRecipientQuestions.mockResolvedValue({ ...THREAD, unread: 2 });
    mocks.markQuestionsSeen.mockResolvedValue({ ...THREAD, unread: 0 });
    render(<ChatPanel groupId="g1" layout="rail" />);

    await waitFor(() => expect(screen.getByLabelText('Close chat')).toBeTruthy());
    await act(async () => {
      fireEvent.press(screen.getByLabelText('Close chat'));
    });

    // The open conversation was seen before it closed (1), the other one was not (2).
    await waitFor(() => expect(screen.getByText('Chat · 2')).toBeTruthy());
    expect(screen.queryByText('What size do you take?')).toBeNull();
    expect(mocks.markQuestionsSeen).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.press(screen.getByText('Chat · 2'));
    });
    await waitFor(() => expect(screen.getByLabelText('Close chat')).toBeTruthy());
  });

  it('remembers being closed', async () => {
    (AsyncStorage as unknown as { getItem: jest.Mock }).getItem.mockResolvedValueOnce('closed');
    render(<ChatPanel groupId="g1" layout="rail" />);

    await waitFor(() => expect(screen.getByText('Chat')).toBeTruthy());
    expect(screen.queryByLabelText('Close chat')).toBeNull();
  });
});

describe('sending', () => {
  it('sends the giver’s question and clears the box', async () => {
    mocks.askQuestion.mockResolvedValue({ ...THREAD, messages: [...THREAD.messages] });
    render(<ChatPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByLabelText('Send anonymously')).toBeTruthy());

    fireEvent.changeText(screen.getByLabelText('Ask about their gift'), '  Is blue right?  ');
    await act(async () => {
      fireEvent.press(screen.getByLabelText('Send anonymously'));
    });

    // Trimmed, and the label on the button says what pressing it does.
    expect(mocks.askQuestion).toHaveBeenCalledWith('token', 'g1', 'Is blue right?');
    expect(screen.getByLabelText('Ask about their gift').props.value).toBe('');
  });

  /** Enter sends on a keyboard only — a phone's return key keeps breaking the line. */
  it.each([
    { os: 'web', sends: true },
    { os: 'ios', sends: false },
  ])('on $os, Enter sends: $sends', async ({ os, sends }) => {
    const original = Platform.OS;
    Object.defineProperty(Platform, 'OS', { value: os, configurable: true });
    try {
      mocks.askQuestion.mockResolvedValue(THREAD);
      render(<ChatPanel groupId="g1" />);
      await waitFor(() => expect(screen.getByLabelText('Ask about their gift')).toBeTruthy());
      const box = screen.getByLabelText('Ask about their gift');

      // Shift+Enter is a line break everywhere.
      fireEvent.changeText(box, 'Line one');
      await act(async () => {
        fireEvent(box, 'keyPress', { nativeEvent: { key: 'Enter', shiftKey: true }, preventDefault: jest.fn() });
      });
      expect(mocks.askQuestion).not.toHaveBeenCalled();

      const preventDefault = jest.fn();
      await act(async () => {
        fireEvent(box, 'keyPress', { nativeEvent: { key: 'Enter' }, preventDefault });
      });
      if (sends) {
        expect(mocks.askQuestion).toHaveBeenCalledWith('token', 'g1', 'Line one');
        // The newline never lands in the box: the key was consumed by the send.
        expect(preventDefault).toHaveBeenCalled();
      } else {
        expect(mocks.askQuestion).not.toHaveBeenCalled();
        expect(preventDefault).not.toHaveBeenCalled();
      }
    } finally {
      Object.defineProperty(Platform, 'OS', { value: original, configurable: true });
    }
  });

  it('will not send an empty question', async () => {
    render(<ChatPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByLabelText('Send anonymously')).toBeTruthy());

    fireEvent.changeText(screen.getByLabelText('Ask about their gift'), '   ');
    await act(async () => {
      fireEvent.press(screen.getByLabelText('Send anonymously'));
    });

    expect(mocks.askQuestion).not.toHaveBeenCalled();
  });

  it('keeps the draft when the send fails, and says why', async () => {
    mocks.askQuestion.mockRejectedValue(new Error('Give it 2 seconds between messages.'));
    render(<ChatPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByLabelText('Send anonymously')).toBeTruthy());

    fireEvent.changeText(screen.getByLabelText('Ask about their gift'), 'Again?');
    await act(async () => {
      fireEvent.press(screen.getByLabelText('Send anonymously'));
    });

    expect(screen.getByText('Give it 2 seconds between messages.')).toBeTruthy();
    expect(screen.getByLabelText('Ask about their gift').props.value).toBe('Again?');
  });

  /**
   * There is no ceiling. The composer is governed by `can_send` alone, so a thread of any length
   * still offers the box — the server stopped counting, and the app never did.
   */
  it('still offers the composer on a long thread', async () => {
    mocks.getGiverQuestions.mockResolvedValue({
      ...THREAD,
      messages: Array.from({ length: 200 }, (_, index) => ({
        message_id: `m${index}`,
        author: index % 2 === 0 ? 'giver' : 'recipient',
        body: `Message ${index}`,
        created_at: 'now',
      })),
    });
    render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(screen.getByText('Message 199')).toBeTruthy());
    expect(screen.getByLabelText('Send anonymously')).toBeTruthy();
    expect(screen.getByLabelText('Ask about their gift')).toBeTruthy();
  });
});

/**
 * A reply lands while you are looking. There is no push channel, so an open panel asks again on a
 * timer — quietly: a refresh that fails shows nothing, and a refresh never runs over a send.
 */
describe('refreshing', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('picks up the other side’s reply without a reload', async () => {
    mocks.getGiverQuestions.mockResolvedValueOnce({ ...THREAD, messages: [THREAD.messages[0]!] });
    render(<ChatPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByText('What size do you take?')).toBeTruthy());
    expect(screen.queryByText('Medium, thanks.')).toBeNull();

    mocks.getGiverQuestions.mockResolvedValue(THREAD);
    await act(async () => {
      jest.advanceTimersByTime(15_000);
    });

    await waitFor(() => expect(screen.getByText('Medium, thanks.')).toBeTruthy());
  });

  it('says nothing when a refresh fails', async () => {
    render(<ChatPanel groupId="g1" />);
    await waitFor(() => expect(screen.getByText('Medium, thanks.')).toBeTruthy());

    mocks.getGiverQuestions.mockRejectedValue(new ApiError(500, 'x', 'Something broke.'));
    await act(async () => {
      jest.advanceTimersByTime(15_000);
    });

    expect(screen.queryByText('Something broke.')).toBeNull();
    // And the thread it already had is still on the screen.
    expect(screen.getByText('Medium, thanks.')).toBeTruthy();
  });
});

describe('blocking', () => {
  it('offers the switch to the recipient only', async () => {
    mocks.setQuestionsBlocked.mockResolvedValue({ ...THREAD, blocked: true, can_send: true });
    await openRecipient();
    await waitFor(() =>
      expect(screen.getByLabelText('Allow anonymous questions about my gift')).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByLabelText('Allow anonymous questions about my gift'));
    });
    // The switch reads "allow", so turning it off is a block. Inverted once, here, rather than the
    // panel offering a control labelled by what it takes away.
    expect(mocks.setQuestionsBlocked).toHaveBeenCalledWith('token', 'g1', true);
  });

  it('gives the giver no switch and no box once questions are off', async () => {
    mocks.getGiverQuestions.mockResolvedValue({
      ...THREAD,
      blocked: true,
      can_send: false,
      blocked_reason: 'Questions are turned off for this gift.',
    });

    render(<ChatPanel groupId="g1" />);

    await waitFor(() =>
      expect(screen.getByText('Questions are turned off for this gift.')).toBeTruthy());
    expect(screen.queryByLabelText('Send anonymously')).toBeNull();
    expect(screen.queryByLabelText('Allow anonymous questions about my gift')).toBeNull();
  });
});

/**
 * A thread that correctly does not exist is not an error to report.
 *
 * Someone sitting out has no assignment, and a draw reset between load and render leaves the old
 * conversation unreachable. Both answer 4xx, and both mean "there is nothing here" — a red bar
 * would be telling the participant something went wrong when nothing did.
 */
describe('when there is no conversation', () => {
  it.each([403, 404, 409])('renders nothing at all on %i', async (status) => {
    mocks.getGiverQuestions.mockRejectedValue(new ApiError(status, 'x', 'no'));
    mocks.getRecipientQuestions.mockRejectedValue(new ApiError(status, 'x', 'no'));

    const { toJSON } = render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(toJSON()).toBeNull());
  });

  /** One conversation missing is not both: the panel shows the one it has and offers no switch. */
  it('shows only the conversation that exists', async () => {
    mocks.getGiverQuestions.mockRejectedValue(new ApiError(404, 'x', 'no'));

    render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(screen.getByText('Questions about your gift')).toBeTruthy());
    expect(screen.queryByText('About their gift')).toBeNull();
    // "Your Secret Santa" still appears — as the caption on the bubbles, not as a tab.
    expect(screen.queryByRole('button', { name: 'Your Secret Santa' })).toBeNull();
  });

  it('does report a failure it cannot explain away', async () => {
    mocks.getGiverQuestions.mockRejectedValue(new ApiError(500, 'x', 'Something broke.'));

    render(<ChatPanel groupId="g1" />);

    await waitFor(() => expect(screen.getByText('Something broke.')).toBeTruthy());
  });
});
