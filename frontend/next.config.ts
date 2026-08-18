import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: FastAPI serves the built files, so there is no Node
  // server at runtime and no second origin to configure CORS for.
  output: "export",
  // Emits <route>/index.html, which matches how the backend resolves paths.
  trailingSlash: true,
  // No image optimization server exists in a static export.
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
