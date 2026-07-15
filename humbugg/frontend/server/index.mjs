import { createRequestHandler } from '@react-router/architect';

import * as build from '../build/server/index.js';

export const handler = createRequestHandler({ build });
