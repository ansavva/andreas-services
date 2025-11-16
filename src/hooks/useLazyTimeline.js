import { useCallback, useEffect, useRef, useState } from 'react';

const PAGE_SIZE = 8;
const API_BASE_PATH = (import.meta.env.VITE_API_BASE_PATH || '/api').replace(/\/$/, '');

function buildApiUrl(path, searchParams) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const query = searchParams?.toString();
  return `${API_BASE_PATH}${normalizedPath}${query ? `?${query}` : ''}`;
}

async function requestEvents(params = {}) {
  const search = new URLSearchParams();
  if (params.cursorId) {
    search.set('cursorId', params.cursorId);
  }
  if (params.direction) {
    search.set('direction', params.direction);
  }
  if (params.limit) {
    search.set('limit', String(params.limit));
  }

  const query = search.toString();
  const url = buildApiUrl('/events', query ? search : undefined);
  const response = await fetch(url);
  if (!response.ok) {
    const raw = await response.text();
    let message = 'Failed to fetch events.';
    try {
      const data = JSON.parse(raw);
      message = data.message || message;
    } catch (parseError) {
      message = raw || message;
    }
    throw new Error(message);
  }
  return response.json();
}

async function requestEventsAround(date, limit) {
  const search = new URLSearchParams();
  if (date) {
    search.set('date', date);
  }
  if (limit) {
    search.set('limit', String(limit));
  }

  const query = search.toString();
  const response = await fetch(buildApiUrl('/events/around', query ? search : undefined));
  if (!response.ok) {
    const raw = await response.text();
    let message = 'Failed to fetch events.';
    try {
      const data = JSON.parse(raw);
      message = data.message || message;
    } catch (parseError) {
      message = raw || message;
    }
    throw new Error(message);
  }
  return response.json();
}

async function requestSearchEvents(query, limit) {
  const search = new URLSearchParams();
  if (query) {
    search.set('query', query);
  }
  if (limit) {
    search.set('limit', String(limit));
  }

  const queryString = search.toString();
  const response = await fetch(buildApiUrl('/events/search', queryString ? search : undefined));
  if (!response.ok) {
    const raw = await response.text();
    let message = 'Failed to search events.';
    try {
      const data = JSON.parse(raw);
      message = data.message || message;
    } catch (parseError) {
      message = raw || message;
    }
    throw new Error(message);
  }
  const data = await response.json();
  return data.events ?? [];
}

async function createRemoteEvent(payload) {
  const response = await fetch(buildApiUrl('/events'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.message || 'Failed to create event.');
  }

  return response.json();
}

async function updateRemoteEvent(id, payload) {
  const response = await fetch(buildApiUrl(`/events/${id}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.message || 'Failed to update event.');
  }

  return response.json();
}

async function deleteRemoteEvent(id) {
  const response = await fetch(buildApiUrl(`/events/${id}`), {
    method: 'DELETE'
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.message || 'Failed to delete event.');
  }

  return response.json();
}

export function useLazyTimeline() {
  const [events, setEvents] = useState([]);
  const [hasMorePast, setHasMorePast] = useState(false);
  const [hasMoreFuture, setHasMoreFuture] = useState(false);
  const [error, setError] = useState(null);
  const [windowSize, setWindowSize] = useState(PAGE_SIZE);
  const [loadingDirection, setLoadingDirection] = useState(null);
  const [isInitializing, setIsInitializing] = useState(true);
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  const eventsRef = useRef(events);
  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  const refreshWindow = useCallback(
    async (cursorId) => {
      try {
        setLoadingDirection((current) => current ?? 'refresh');
        const data = await requestEvents({ cursorId, limit: windowSize });
        setEvents(data.events);
        setHasMorePast(data.hasMorePast);
        setHasMoreFuture(data.hasMoreFuture);
        setWindowSize((current) => Math.max(current, data.events.length || PAGE_SIZE));
        setError(null);
      } catch (refreshError) {
        setError(refreshError.message);
        throw refreshError;
      } finally {
        setLoadingDirection((current) => (current === 'refresh' ? null : current));
      }
    },
    [windowSize]
  );

  useEffect(() => {
    let isActive = true;
    (async () => {
      try {
        setIsInitializing(true);
        const data = await requestEvents({ limit: PAGE_SIZE });
        if (!isActive) {
          return;
        }
        setEvents(data.events);
        setHasMorePast(data.hasMorePast);
        setHasMoreFuture(data.hasMoreFuture);
        setWindowSize(data.events.length || PAGE_SIZE);
        setError(null);
      } catch (initialError) {
        if (isActive) {
          setError(initialError.message);
        }
      } finally {
        if (isActive) {
          setIsInitializing(false);
        }
      }
    })();

    return () => {
      isActive = false;
    };
  }, []);

  const loadMorePast = useCallback(async () => {
    if (!hasMorePast || loadingDirection) {
      return;
    }
    const first = eventsRef.current[0];
    if (!first) {
      return;
    }

    try {
      setLoadingDirection('past');
      const data = await requestEvents({ cursorId: first.id, direction: 'past', limit: PAGE_SIZE });
      setEvents((current) => [...data.events, ...current]);
      setHasMorePast(data.hasMorePast);
      if (typeof data.hasMoreFuture === 'boolean') {
        setHasMoreFuture(data.hasMoreFuture);
      }
      setWindowSize((current) => current + (data.events.length || 0));
      setError(null);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoadingDirection(null);
    }
  }, [hasMorePast, loadingDirection]);

  const loadMoreFuture = useCallback(async () => {
    if (!hasMoreFuture || loadingDirection) {
      return;
    }
    const last = eventsRef.current[eventsRef.current.length - 1];
    if (!last) {
      return;
    }

    try {
      setLoadingDirection('future');
      const data = await requestEvents({ cursorId: last.id, direction: 'future', limit: PAGE_SIZE });
      setEvents((current) => [...current, ...data.events]);
      setHasMoreFuture(data.hasMoreFuture);
      if (typeof data.hasMorePast === 'boolean') {
        setHasMorePast(data.hasMorePast);
      }
      setWindowSize((current) => current + (data.events.length || 0));
      setError(null);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoadingDirection(null);
    }
  }, [hasMoreFuture, loadingDirection]);

  const addEvent = useCallback(
    async (payload) => {
      const created = await createRemoteEvent(payload);
      await refreshWindow(created.id);
      return created;
    },
    [refreshWindow]
  );

  const editEvent = useCallback(
    async (id, payload) => {
      const updated = await updateRemoteEvent(id, payload);
      await refreshWindow(updated.id);
      return updated;
    },
    [refreshWindow]
  );

  const removeEvent = useCallback(
    async (id) => {
      await deleteRemoteEvent(id);
      const currentEvents = eventsRef.current;
      const fallback = currentEvents.find((event) => event.id !== id);
      const cursorId = fallback ? fallback.id : undefined;
      try {
        await refreshWindow(cursorId);
      } catch (refreshError) {
        if (!cursorId) {
          setEvents([]);
          setHasMorePast(false);
          setHasMoreFuture(false);
        }
        throw refreshError;
      }
    },
    [refreshWindow]
  );

  const jumpToDate = useCallback(
    async (date) => {
      if (!date) {
        return;
      }
      try {
        setLoadingDirection((current) => current ?? 'refresh');
        const data = await requestEventsAround(date, windowSize);
        setEvents(data.events);
        setHasMorePast(data.hasMorePast);
        setHasMoreFuture(data.hasMoreFuture);
        setWindowSize((current) => Math.max(current, data.events.length || PAGE_SIZE));
        setError(null);
      } catch (jumpError) {
        setError(jumpError.message);
        throw jumpError;
      } finally {
        setLoadingDirection((current) => (current === 'refresh' ? null : current));
      }
    },
    [windowSize]
  );

  const jumpToEvent = useCallback(
    async (eventId) => {
      if (!eventId) {
        return;
      }
      try {
        setLoadingDirection((current) => current ?? 'refresh');
        await refreshWindow(eventId);
        setError(null);
      } catch (jumpError) {
        setError(jumpError.message);
        throw jumpError;
      } finally {
        setLoadingDirection((current) => (current === 'refresh' ? null : current));
      }
    },
    [refreshWindow]
  );

  const searchEvents = useCallback(async (term) => {
    const query = term?.trim();
    if (!query) {
      setSearchResults([]);
      setSearchError('');
      return [];
    }

    setIsSearching(true);
    try {
      const results = await requestSearchEvents(query, PAGE_SIZE * 2);
      setSearchResults(results);
      setSearchError('');
      return results;
    } catch (searchErr) {
      setSearchError(searchErr.message);
      throw searchErr;
    } finally {
      setIsSearching(false);
    }
  }, []);

  return {
    events,
    loadMorePast,
    loadMoreFuture,
    hasMorePast,
    hasMoreFuture,
    isLoading: isInitializing || Boolean(loadingDirection),
    error,
    addEvent,
    editEvent,
    removeEvent,
    jumpToDate,
    jumpToEvent,
    searchResults,
    searchEvents,
    isSearching,
    searchError
  };
}
