import { createServer } from './app.js';

const PORT = process.env.PORT ? Number.parseInt(process.env.PORT, 10) : 5000;
const app = await createServer();

app.listen(PORT, () => {
  console.log(`Events API listening on port ${PORT}`);
});
