/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        zyricon: {
          sidebar: "#07070B",
          canvas: "#0D0B14",
          card: "#12101B",
          input: "#161321",
          border: "rgba(255, 255, 255, 0.08)",
          accent: "#8B5CF6",
          crimson: "#C50337",
        }
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"Golos Text"', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      }
    },
  },
  plugins: [],
}
