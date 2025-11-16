import serverless from 'serverless-http';
import { createServer } from './app.js';

let cachedHandler;

export const apiHandler = async (event, context) => {
  if (!cachedHandler) {
    const app = await createServer();
    cachedHandler = serverless(app);
  }

  return cachedHandler(event, context);
};
