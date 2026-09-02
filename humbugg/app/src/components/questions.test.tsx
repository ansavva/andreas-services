// Anonymous questions (#131), on the app side.
//
// The API sends a SIDE and never a person, so the app has no identity to leak — unless it invents
// one. These tests pin that it does not: the same thread rendered from both seats produces the same
// two labels, "You" and a role, and nothing else.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import type { QuestionThread } from '../types';

const mocks = {
  getGiverQuestions: jest.fn(),
  getRecipientQuestions: jest.fn(),
  askQuestion: jest.fn(),
  replyToQuestion: jest.fn(),
  setQuestionsBlocked: jest.fn(),
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
    },
    ApiError,
  };
});

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({ accessToken: () => Promise.resolve('token'), authenticated: true }),
}));

jest.mock('./shell', () => {
  const { View } = require('react-native');
  return { Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View> };
});

import { QuestionsPanel } from './questions';

const { ApiError } = jest.requireMock('../api/client') as {
  ApiError: new (status: number, code: string, message: string) => Error;
};

/** The exact payload both sides receive — identical, which is the server's guarantee. */
const THREAD: QuestionThread = {
  messages: [
    { message_id: 'm1', author: 'giver', body: 'What size do you take?', created_at: 'now' },
    { message_id: 'm2', author: 'recipient', body: 'Medium, thanks.', created_at: 'now' },
  ],
  blocked: false,
  can_send: true,
  blocked_reason: null,
  message_limit: 50,
};

beforeEach(() => {
  jest.clearAllMocks();
  mocks.getGiverQuestions.mockResolvedValue(THREAD);
  mocks.getRecipientQuestions.mockResolvedValue(THREAD);
});

describe('the thread', () => {
  it('labels the giver’s own message "You" and the reply by role', async () => {
    render(<QuestionsPanel groupId="g1" side="giver" />);

    await waitFor(() => expect(screen.getByText('What size do you take?')).toBeTruthy());
    expect(screen.getByText('You')).toBeTruthy();
    expect(screen.getByText('Them')).toBeTruthy();
  });

  /**
   * The same payload from the other seat. "You" and "Them" simply swap — the recipient is told
   * "Your giver", which is a role, and there is no branch anywhere that could produce a name.
   */
  it('labels the same thread from the recipient’s seat without naming anyone', async () => {
    render(<QuestionsPanel groupId="g1" side="recipient" />);

    await waitFor(() => expect(screen.getByText('Medium, thanks.')).toBeTruthy());
    expect(screen.getByText('You')).toBeTruthy();
    expect(screen.getByText('Your giver')).toBeTruthy();
    // Whatever else the screen says, it never claims to know who asked.
    expect(screen.getByText(/Humbugg does not tell you who/)).toBeTruthy();
  });

  it('gives a screen reader one sentence per message rather than two loose lines', async () => {
    render(<QuestionsPanel groupId="g1" side="recipient" />);

    await waitFor(() =>
      expect(screen.getByLabelText('Your giver: What size do you take?')).toBeTruthy());
    expect(screen.getByLabelText('You: Medium, thanks.')).toBeTruthy();
  });
});

describe('sending', () => {
  it('sends the giver’s question and clears the box', async () => {
    mocks.askQuestion.mockResolvedValue({ ...THREAD, messages: [...THREAD.messages] });
    render(<QuestionsPanel groupId="g1" side="giver" />);
    await waitFor(() => expect(screen.getByText('Send anonymously')).toBeTruthy());

    fireEvent.changeText(screen.getByLabelText('Ask about their gift'), '  Is blue right?  ');
    await act(async () => {
      fireEvent.press(screen.getByText('Send anonymously'));
    });

    // Trimmed, and the label on the button says what pressing it does.
    expect(mocks.askQuestion).toHaveBeenCalledWith('token', 'g1', 'Is blue right?');
    expect(screen.getByLabelText('Ask about their gift').props.value).toBe('');
  });

  it('will not send an empty question', async () => {
    render(<QuestionsPanel groupId="g1" side="giver" />);
    await waitFor(() => expect(screen.getByText('Send anonymously')).toBeTruthy());

    fireEvent.changeText(screen.getByLabelText('Ask about their gift'), '   ');
    await act(async () => {
      fireEvent.press(screen.getByText('Send anonymously'));
    });

    expect(mocks.askQuestion).not.toHaveBeenCalled();
  });

  it('keeps the draft when the send fails, and says why', async () => {
    mocks.askQuestion.mockRejectedValue(new Error('Give it 30 seconds between messages.'));
    render(<QuestionsPanel groupId="g1" side="giver" />);
    await waitFor(() => expect(screen.getByText('Send anonymously')).toBeTruthy());

    fireEvent.changeText(screen.getByLabelText('Ask about their gift'), 'Again?');
    await act(async () => {
      fireEvent.press(screen.getByText('Send anonymously'));
    });

    expect(screen.getByText('Give it 30 seconds between messages.')).toBeTruthy();
    expect(screen.getByLabelText('Ask about their gift').props.value).toBe('Again?');
  });
});

describe('blocking', () => {
  it('offers the switch to the recipient only', async () => {
    mocks.setQuestionsBlocked.mockResolvedValue({ ...THREAD, blocked: true, can_send: true });
    render(<QuestionsPanel groupId="g1" side="recipient" />);
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

    render(<QuestionsPanel groupId="g1" side="giver" />);

    await waitFor(() =>
      expect(screen.getByText('Questions are turned off for this gift.')).toBeTruthy());
    expect(screen.queryByText('Send anonymously')).toBeNull();
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

    const { toJSON } = render(<QuestionsPanel groupId="g1" side="giver" />);

    await waitFor(() => expect(toJSON()).toBeNull());
  });

  it('does report a failure it cannot explain away', async () => {
    mocks.getGiverQuestions.mockRejectedValue(new ApiError(500, 'x', 'Something broke.'));

    render(<QuestionsPanel groupId="g1" side="giver" />);

    await waitFor(() => expect(screen.getByText('Something broke.')).toBeTruthy());
  });
});
