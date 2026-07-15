import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the production Docker image
  output: "standalone",
  async rewrites() {
    // The FastAPI backend has no CORS middleware; proxying through Next
    // keeps the browser same-origin.
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
