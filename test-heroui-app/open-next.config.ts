import type { OpenNextConfig } from '@opennextjs/cloudflare';

const config: OpenNextConfig = {
  default: {
    override: {
      wrapper: 'cloudflare-node',
      converter: 'edge',
      incrementalCache: 'cloudflare-kv',
      tagCache: 'cloudflare-kv',
      queue: 'sqs',
    },
  },
};

export default config;
