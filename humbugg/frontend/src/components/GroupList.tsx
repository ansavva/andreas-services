import { Group } from '../types';

interface GroupListProps {
  groups: Group[];
  selectedGroupId: string | null;
  loading: boolean;
  onSelect: (groupId: string) => void;
  onRefresh: () => void;
  onDelete: (groupId: string) => void;
}

const cardClass =
  'rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-emerald-200 hover:shadow-md';

export default function GroupList({ groups, selectedGroupId, loading, onSelect, onRefresh, onDelete }: GroupListProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Your groups</h2>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">{groups.length} active</p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="rounded-full border border-slate-300 px-4 py-1.5 text-xs font-semibold text-slate-600 hover:border-slate-400 hover:text-slate-900"
        >
          Refresh
        </button>
      </div>
      {loading && !groups.length ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading groups…</div>
      ) : null}
      {groups.length === 0 && !loading ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
          No groups found yet. Create one using the form on the right.
        </div>
      ) : null}
      {groups.map((group) => {
        const isSelected = selectedGroupId === group.id;
        return (
          <article
            key={group.id}
            className={`${cardClass} ${isSelected ? 'border-emerald-200 ring-2 ring-emerald-100' : ''}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold text-slate-900">{group.name}</h3>
                {group.description ? <p className="mt-1 text-sm text-slate-500">{group.description}</p> : null}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => onSelect(group.id)}
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    isSelected ? 'bg-emerald-600 text-white' : 'border border-slate-200 text-slate-700'
                  }`}
                >
                  {isSelected ? 'Selected' : 'Open'}
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(group.id)}
                  className="rounded-full border border-transparent px-3 py-1 text-xs font-semibold text-rose-500 hover:bg-rose-50"
                >
                  Delete
                </button>
              </div>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-500">
              <div>
                <dt className="uppercase tracking-[0.3em]">Signup</dt>
                <dd>{group.signUpDeadline ? new Date(group.signUpDeadline).toLocaleDateString() : '—'}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-[0.3em]">Event</dt>
                <dd>{group.eventDate ? new Date(group.eventDate).toLocaleDateString() : '—'}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-[0.3em]">Budget</dt>
                <dd>{group.spendingLimit ? `$${group.spendingLimit.toFixed(2)}` : '—'}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-[0.3em]">Members</dt>
                <dd>{group.groupMembers.length}</dd>
              </div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}
