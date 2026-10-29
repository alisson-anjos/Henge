import type { NextConfig } from 'next';
const nextConfig: NextConfig = {
  // Extra hosts allowed to open `next dev` (comma list, e.g. a LAN or tunnel address); set it in .env.local.
  allowedDevOrigins: (process.env.HENGE_DEV_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean),
};
export default nextConfig;
