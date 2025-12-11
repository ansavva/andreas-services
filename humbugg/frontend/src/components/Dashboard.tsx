import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Group, GroupMember } from '../types';
import { createGroup, deleteGroup, deleteGroupMember, fetchGroup, fetchGroups, triggerMatches } from '../api/client';
import GroupDetails from './GroupDetails';
import GroupList from './GroupList';
import CreateGroupForm from './CreateGroupForm';

export default function Dashboard() {
  const auth = useAuth();
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = auth.token;

  const refreshGroups = useCallback(async () => {
    if (!token) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGroups({ baseUrl: auth.apiBaseUrl, token });
      setGroups(data);
      if (data.length && !selectedGroupId) {
        setSelectedGroupId(data[0].id);
      }
    } catch (err) {
      console.error(err);
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to load groups.');
      }
    } finally {
      setLoading(false);
    }
  }, [auth.apiBaseUrl, selectedGroupId, token]);

  useEffect(() => {
    refreshGroups();
  }, [refreshGroups]);

  const handleSelectGroup = useCallback(
    async (groupId: string) => {
      if (!token) return;
      setSelectedGroupId(groupId);
      try {
        const data = await fetchGroup(groupId, { baseUrl: auth.apiBaseUrl, token });
        setGroups((prev) => prev.map((group) => (group.id === data.id ? data : group)));
      } catch (err) {
        console.error(err);
        setError('Unable to load the selected group.');
      }
    },
    [auth.apiBaseUrl, token]
  );

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === selectedGroupId) ?? null,
    [groups, selectedGroupId]
  );

  const handleCreateGroup = useCallback(
    async (payload: Parameters<typeof createGroup>[0]) => {
      if (!token) return;
      await createGroup(payload, { baseUrl: auth.apiBaseUrl, token });
      await refreshGroups();
    },
    [auth.apiBaseUrl, refreshGroups, token]
  );

  const handleDeleteMember = useCallback(
    async (member: GroupMember) => {
      if (!token) return;
      await deleteGroupMember(member.id, { baseUrl: auth.apiBaseUrl, token });
      const updated = await fetchGroup(member.groupId, { baseUrl: auth.apiBaseUrl, token });
      setGroups((prev) => prev.map((group) => (group.id === updated.id ? updated : group)));
    },
    [auth.apiBaseUrl, token]
  );

  const handleDeleteGroup = useCallback(
    async (groupId: string) => {
      if (!window.confirm('Delete this group? This cannot be undone.')) {
        return;
      }
      if (!token) return;
      await deleteGroup(groupId, { baseUrl: auth.apiBaseUrl, token });
      await refreshGroups();
      setSelectedGroupId((current) => (current === groupId ? null : current));
    },
    [auth.apiBaseUrl, refreshGroups, token]
  );

  const handleCreateMatches = useCallback(
    async (groupId: string) => {
      if (!token) return;
      const updated = await triggerMatches(groupId, { baseUrl: auth.apiBaseUrl, token });
      setGroups((prev) => prev.map((group) => (group.id === updated.id ? updated : group)));
    },
    [auth.apiBaseUrl, token]
  );

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2 rounded-2xl bg-white p-6 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Welcome</p>
          <h1 className="text-2xl font-semibold text-slate-900">
            {auth.profile ? `${auth.profile.firstName || 'Friend'} ${auth.profile.lastName || ''}` : 'Humbugg'}
          </h1>
          {auth.profile?.email ? <p className="text-sm text-slate-500">{auth.profile.email}</p> : null}
        </div>
        <button
          type="button"
          onClick={auth.logout}
          className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400 hover:text-slate-900"
        >
          Sign out
        </button>
      </header>

      {error ? <div className="rounded-lg bg-rose-50 p-4 text-sm text-rose-700">{error}</div> : null}

      <section className="grid gap-6 lg:grid-cols-[2fr_3fr]">
        <GroupList
          groups={groups}
          loading={loading}
          selectedGroupId={selectedGroup?.id ?? null}
          onSelect={handleSelectGroup}
          onRefresh={refreshGroups}
          onDelete={handleDeleteGroup}
        />
        <CreateGroupForm profile={auth.profile} onCreate={handleCreateGroup} />
      </section>

      <section>
        {selectedGroup ? (
          <GroupDetails
            group={selectedGroup}
            onRefresh={() => handleSelectGroup(selectedGroup.id)}
            onDeleteMember={handleDeleteMember}
            onCreateMatches={handleCreateMatches}
          />
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
            Select a group to inspect members and run matches.
          </div>
        )}
      </section>
    </div>
  );
}
