import express from 'express';
import cors from 'cors';
import { createEventsStore } from './store/eventsStore.js';

const PORT = process.env.PORT ? Number.parseInt(process.env.PORT, 10) : 5000;
const app = express();
app.use(cors());
app.use(express.json());

const eventsStore = await createEventsStore();

app.get('/api/events', (request, response) => {
  try {
    const { cursorId, direction, limit } = request.query;
    const result = eventsStore.query({ cursorId, direction, limit });
    response.json(result);
  } catch (error) {
    response.status(400).json({ message: error.message });
  }
});

app.get('/api/events/around', (request, response) => {
  try {
    const { date, limit } = request.query;
    if (!date) {
      throw new Error('date query parameter is required.');
    }
    const result = eventsStore.queryAroundDate(date, limit);
    response.json(result);
  } catch (error) {
    response.status(400).json({ message: error.message });
  }
});

app.get('/api/events/search', (request, response) => {
  try {
    const { query, limit } = request.query;
    const events = eventsStore.searchEvents(query, limit);
    response.json({ events });
  } catch (error) {
    response.status(400).json({ message: error.message });
  }
});

app.post('/api/events', async (request, response) => {
  try {
    const event = await eventsStore.createEvent(request.body);
    response.status(201).json(event);
  } catch (error) {
    response.status(400).json({ message: error.message });
  }
});

app.put('/api/events/:id', async (request, response) => {
  const { id } = request.params;
  try {
    const event = await eventsStore.updateEvent(id, request.body);
    response.json(event);
  } catch (error) {
    const status = error.message === 'event not found.' ? 404 : 400;
    response.status(status).json({ message: error.message });
  }
});

app.delete('/api/events/:id', async (request, response) => {
  const { id } = request.params;
  try {
    const event = await eventsStore.deleteEvent(id);
    response.json(event);
  } catch (error) {
    const status = error.message === 'event not found.' ? 404 : 400;
    response.status(status).json({ message: error.message });
  }
});

app.listen(PORT, () => {
  console.log(`Events API listening on port ${PORT}`);
});
