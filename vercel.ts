import { type VercelConfig } from '@vercel/config/v1';

export const config: VercelConfig = {
  framework: null,
  crons: [
    { path: '/api/digest', schedule: '0 14 * * *' },
  ],
};
