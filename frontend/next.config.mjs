/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Subdomain deployment (saas.ramyaai.tech) - no basePath needed.
  // The existing site on ramyaai.tech is a separate Vercel project and stays untouched.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
