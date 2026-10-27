import type { NextConfig } from "next";

// The browser talks to Next.js same-origin at /api/*; Next proxies to the
// FastAPI backend (OpenCV + agent). No CORS, and SSE streaming passes through.
const FASTAPI_ORIGIN = process.env.FASTAPI_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${FASTAPI_ORIGIN}/:path*` },
    ];
  },
};

export default nextConfig;
