import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // FastAPI serves the built files, so there is no Node server at runtime.
  output: "export",
  // Emits <route>/index.html, which matches how the backend resolves paths.
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
