import { FormEvent, useState } from 'react';
import { GroupPayload } from '../api/client';
import { Profile } from '../types';

interface Props {
  profile: Profile | null;
  onCreate: (payload: GroupPayload) => Promise<void>;
}

const inputClass =
  'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-200';

export default function CreateGroupForm({ profile, onCreate }: Props) {
  const [state, setState] = useState({
    name: '',
    description: '',
    spendingLimit: '50',
    signUpDeadline: '',
    eventDate: '',
    secretQuestion: '',
    secretAnswer: ''
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleChange = (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = event.target;
    setState((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (!profile) {
      setError('Load your profile before creating a group.');
      return;
    }
    setSaving(true);
    try {
      const payload: GroupPayload = {
        Name: state.name,
        Description: state.description,
        SecretQuestion: state.secretQuestion,
        SecretQuestionAnswer: state.secretAnswer,
        SignUpDeadline: state.signUpDeadline || undefined,
        EventDate: state.eventDate || undefined,
        SpendingLimit: state.spendingLimit ? Number(state.spendingLimit) : undefined,
        GroupMembers: [
          {
            UserId: profile.id,
            FirstName: profile.firstName,
            LastName: profile.lastName,
            IsAdmin: true,
            IsParticipating: true
          }
        ]
      };
      await onCreate(payload);
      setState({
        name: '',
        description: '',
        spendingLimit: '50',
        signUpDeadline: '',
        eventDate: '',
        secretQuestion: '',
        secretAnswer: ''
      });
      setSuccess('Group created.');
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Unable to create group.');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">New group</h2>
      <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Organize a fresh exchange</p>

      <form className="mt-4 flex flex-col gap-4" onSubmit={handleSubmit}>
        <label className="flex flex-col gap-1 text-sm text-slate-800">
          Name
          <input
            name="name"
            required
            value={state.name}
            onChange={handleChange}
            className={inputClass}
            placeholder="The Savva Family 2024"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-800">
          Description
          <textarea
            name="description"
            value={state.description}
            onChange={handleChange}
            className={`${inputClass} min-h-[80px]`}
            placeholder="Share context, gift rules, or links."
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm text-slate-800">
            Spending limit
            <input name="spendingLimit" value={state.spendingLimit} onChange={handleChange} className={inputClass} />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-800">
            Signup deadline
            <input type="date" name="signUpDeadline" value={state.signUpDeadline} onChange={handleChange} className={inputClass} />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-800">
            Event date
            <input type="date" name="eventDate" value={state.eventDate} onChange={handleChange} className={inputClass} />
          </label>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm text-slate-800">
            Secret question
            <input
              name="secretQuestion"
              value={state.secretQuestion}
              onChange={handleChange}
              className={inputClass}
              placeholder="e.g. What is aunt Marie's nickname?"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-800">
            Answer
            <input name="secretAnswer" value={state.secretAnswer} onChange={handleChange} className={inputClass} />
          </label>
        </div>
        <button
          type="submit"
          disabled={saving}
          className="rounded-full bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          {saving ? 'Creating…' : 'Create group'}
        </button>
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        {success ? <p className="text-sm text-emerald-600">{success}</p> : null}
      </form>
    </div>
  );
}
