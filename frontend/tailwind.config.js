/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b0b0f",         // page background
        surface: "#0f1117",    // cards
        panel: "#1b1d24",      // inputs
        edge: "#2b2f3a",       // borders
        text: {
          DEFAULT: "#e5e7eb",  // main text
          soft: "#c7cbd4",     // slightly softer
          muted: "#9ca3af",    // secondary
        },
      },
    },
  },
  plugins: [],
};