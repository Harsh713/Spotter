/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        chai: {
          bg: "#0c0d10",
          card: "rgba(18, 20, 26, 0.7)",
          hairline: "rgba(255, 255, 255, 0.08)",
          hairlineHover: "rgba(255, 255, 255, 0.15)",
          activeTab: "#252830",
          muted: "#94a3b8",
          cream: "#f1f5f9"
        },
        risk: {
          low: "#10b981",
          moderate: "#f59e0b",
          high: "#f97316",
          severe: "#ef4444",
          notravel: "#991b1b"
        }
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif"
        ]
      }
    },
  },
  plugins: [],
}
