import { useMemo, useState } from 'react';
import { Group, GroupMember } from '../types';

interface Props {
  group: Group;
  onRefresh: () => void;
  onDeleteMember: (member: GroupMember) => Promise<void>;
  onCreateMatches: (groupId: string) => Promise<void>;
}

export default function GroupDetails({ group, onRefresh, onDeleteMember, onCreateMatches }: Props) {
  const [matchesStatus, setMatchesStatus] = useState<string | null>(null);

  const members = useMemo(() => group.groupMembers, [group.groupMembers]);

  const handleDeleteMember = async (member: GroupMember) => {
    if (!window.confirm(`Remove ${member.firstName} ${member.lastName}?`)) {
      return;
    }
    await onDeleteMember(member);
  };

  const handleCreateMatches = async () => {
    setMatchesStatus(null);
    try {
      await onCreateMatches(group.id);
      setMatchesStatus('Matched participants successfully.');
    } catch (err) {
      if (err instanceof Error) {
        setMatchesStatus(err.message);
      } else {
        setMatchesStatus('Unable to create matches.');
      }
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-4 border-b border-slate-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Selected group</p>
          <h2 className="text-2xl font-semibold text-slate-900">{group.name}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-full border border-slate-300 px-4 py-1.5 text-xs font-semibold text-slate-700 hover:border-slate-400"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={handleCreateMatches}
            className="rounded-full bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
          >
            Create matches
          </button>
        </div>
      </div>

      <dl className="mt-4 grid gap-4 text-sm text-slate-600 sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase tracking-[0.3em] text-slate-400">Signup deadline</dt>
          <dd>{group.signUpDeadline ? new Date(group.signUpDeadline).toLocaleDateString() : '—'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-[0.3em] text-slate-400">Event date</dt>
          <dd>{group.eventDate ? new Date(group.eventDate).toLocaleDateString() : '—'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-[0.3em] text-slate-400">Spending limit</dt>
          <dd>{group.spendingLimit ? `$${group.spendingLimit.toFixed(2)}` : '—'}</dd>
        </div>
      </dl>

      {group.description ? <p className="mt-4 text-sm text-slate-600">{group.description}</p> : null}
      {matchesStatus ? <p className="mt-2 text-xs text-emerald-600">{matchesStatus}</p> : null}

      <section className="mt-6">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-900">Members</h3>
          <span className="text-xs uppercase tracking-[0.3em] text-slate-400">{members.length}</span>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Participants manage their own profile and wish lists inside Humbugg. Admins can remove members or run the match
          after everyone has joined.
        </p>
        <div className="mt-3 space-y-2">
          {members.map((member) => (
            <article
              key={member.id}
              className="rounded-xl border border-slate-200 bg-slate-50 p-4 shadow-sm transition hover:border-emerald-200"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-900">
                    {member.firstName} {member.lastName}
                  </p>
                  <p className="text-xs text-slate-500">
                    {member.isAdmin ? 'Admin' : 'Participant'} • {member.isParticipating ? 'Active' : 'Inactive'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteMember(member)}
                  className="rounded-full border border-transparent px-3 py-1 text-xs font-semibold text-rose-500 hover:bg-rose-50"
                >
                  Remove
                </button>
              </div>
              {member.giftSuggestionsDescription ? (
                <p className="mt-3 text-xs text-slate-600">
                  Wishes: <span className="text-slate-800">{member.giftSuggestionsDescription}</span>
                </p>
              ) : null}
              {member.recipientId ? (
                <p className="mt-2 text-xs text-emerald-600">Matched recipient ID: {member.recipientId}</p>
              ) : null}
            </article>
          ))}
          {!members.length ? (
            <div className="rounded-lg border border-dashed border-slate-300 p-4 text-center text-xs text-slate-500">
              Invite members or let them join via the Humbugg identity portal.
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
