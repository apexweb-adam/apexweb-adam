/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        apex: {
          gold: "#DDBB63",
          dark: "#0A0B0F",
          card: "#11131A",
          border: "#1E2130",
          green: "#22C55E",
          red: "#EF4444",
          blue: "#3B82F6",
          purple: "#8B5CF6",
        },
      },
    },
  },
  plugins: [],
};
