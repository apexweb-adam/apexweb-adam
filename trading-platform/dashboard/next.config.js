/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone only for Docker; Vercel uses its own Next.js integration
  ...(process.env.DOCKER_BUILD === "true" ? { output: "standalone" } : {}),
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000",
  },
};

module.exports = nextConfig;
