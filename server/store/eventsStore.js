import { readFile, writeFile } from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import crypto from 'crypto';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DATA_FILE = path.resolve(__dirname, '../data/events.json');
const SEED_FILE = path.resolve(__dirname, '../data/seedEvents.json');

function sortEvents(events) {
  return [...events].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
}

function clampLimit(limit) {
  const parsed = Number.parseInt(limit, 10);
  if (Number.isNaN(parsed) || parsed <= 0) {
    return 8;
  }
  return Math.min(parsed, 50);
}

function normalizeEventPayload(payload = {}) {
  const { title, date, description } = payload;
  if (!title || !date || !description) {
    throw new Error('title, date, and description are required.');
  }

  const trimmedTitle = title.trim();
  const trimmedDescription = description.trim();

  if (!trimmedTitle || !trimmedDescription) {
    throw new Error('title and description cannot be empty.');
  }

  const isoDate = new Date(date);
  if (Number.isNaN(isoDate.getTime())) {
    throw new Error('date must be a valid ISO-8601 string.');
  }

  return {
    title: trimmedTitle,
    description: trimmedDescription,
    date: isoDate.toISOString().slice(0, 10)
  };
}

class EventsStore {
  constructor() {
    this.events = [];
  }

  async load() {
    let parsed = [];

    try {
      const fileContents = await readFile(DATA_FILE, 'utf-8');
      parsed = JSON.parse(fileContents);
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
    }

    if (!Array.isArray(parsed) || parsed.length === 0) {
      const seedsContents = await readFile(SEED_FILE, 'utf-8');
      parsed = JSON.parse(seedsContents);
      this.events = sortEvents(parsed);
      await this.persist();
      return;
    }

    this.events = sortEvents(parsed);
  }

  async persist() {
    await writeFile(DATA_FILE, JSON.stringify(this.events, null, 2));
  }

  getSnapshot() {
    return sortEvents(this.events);
  }

  query({ cursorId, direction, limit }) {
    const sorted = this.getSnapshot();
    if (!sorted.length) {
      return { events: [], hasMorePast: false, hasMoreFuture: false };
    }

    const windowSize = clampLimit(limit);

    if (!direction) {
      let anchorIndex = Math.floor(sorted.length / 2);
      if (cursorId) {
        const foundIndex = sorted.findIndex((event) => event.id === cursorId);
        if (foundIndex !== -1) {
          anchorIndex = foundIndex;
        }
      }

      let start = Math.max(0, anchorIndex - Math.floor(windowSize / 2));
      let end = Math.min(sorted.length, start + windowSize);

      if (end - start < windowSize) {
        start = Math.max(0, end - windowSize);
      }

      const events = sorted.slice(start, end);

      return {
        events,
        hasMorePast: start > 0,
        hasMoreFuture: end < sorted.length
      };
    }

    const cursorIndex = sorted.findIndex((event) => event.id === cursorId);
    if (cursorIndex === -1) {
      throw new Error('cursorId not found.');
    }

    if (direction === 'past') {
      const endIndex = cursorIndex;
      const startIndex = Math.max(0, endIndex - windowSize);
      const events = sorted.slice(startIndex, endIndex);
      return {
        events,
        hasMorePast: startIndex > 0,
        hasMoreFuture: cursorIndex < sorted.length - 1
      };
    }

    if (direction === 'future') {
      const startIndex = cursorIndex + 1;
      const endIndex = Math.min(sorted.length, startIndex + windowSize);
      const events = sorted.slice(startIndex, endIndex);
      return {
        events,
        hasMorePast: cursorIndex > 0,
        hasMoreFuture: endIndex < sorted.length
      };
    }

    throw new Error('direction must be either "past" or "future".');
  }

  queryAroundDate(date, limit) {
    const sorted = this.getSnapshot();
    if (!sorted.length) {
      return { events: [], hasMorePast: false, hasMoreFuture: false };
    }

    const parsedDate = new Date(date);
    if (Number.isNaN(parsedDate.getTime())) {
      throw new Error('date must be a valid ISO-8601 string.');
    }

    const windowSize = clampLimit(limit);
    const anchorIndex = sorted.findIndex((event) => new Date(event.date).getTime() >= parsedDate.getTime());
    const targetIndex = anchorIndex === -1 ? sorted.length - 1 : anchorIndex;

    let start = Math.max(0, targetIndex - Math.floor(windowSize / 2));
    let end = Math.min(sorted.length, start + windowSize);
    if (end - start < windowSize) {
      start = Math.max(0, end - windowSize);
    }

    const events = sorted.slice(start, end);

    return {
      events,
      hasMorePast: start > 0,
      hasMoreFuture: end < sorted.length
    };
  }

  searchEvents(query, limit) {
    const searchTerm = query?.toString()?.trim();
    if (!searchTerm) {
      throw new Error('query parameter is required.');
    }

    const normalized = searchTerm.toLowerCase();
    const windowSize = clampLimit(limit);

    const matches = this.getSnapshot().filter((event) => {
      return (
        event.title.toLowerCase().includes(normalized) || event.description.toLowerCase().includes(normalized)
      );
    });

    return matches.slice(0, windowSize);
  }

  async createEvent(payload) {
    const data = normalizeEventPayload(payload);
    const newEvent = {
      id: crypto.randomUUID(),
      ...data
    };
    this.events = sortEvents([...this.events, newEvent]);
    await this.persist();
    return newEvent;
  }

  async updateEvent(id, payload) {
    const data = normalizeEventPayload(payload);
    const index = this.events.findIndex((event) => event.id === id);
    if (index === -1) {
      throw new Error('event not found.');
    }

    this.events[index] = { id, ...data };
    this.events = sortEvents(this.events);
    await this.persist();
    return this.events.find((event) => event.id === id);
  }

  async deleteEvent(id) {
    const index = this.events.findIndex((event) => event.id === id);
    if (index === -1) {
      throw new Error('event not found.');
    }

    const [removed] = this.events.splice(index, 1);
    await this.persist();
    return removed;
  }
}

export async function createEventsStore() {
  const store = new EventsStore();
  await store.load();
  return store;
}
