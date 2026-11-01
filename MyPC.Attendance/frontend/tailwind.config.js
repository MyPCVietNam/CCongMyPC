/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#101114",
        panel: "#181B20",
        panel2: "#1E2229",
        line: "#2A2F38",
        ink: "#E8EAED",
        muted: "#9AA3AF",
        brand: "#EAB308",
        ok: "#22C55E",
        warn: "#F59E0B",
        danger: "#EF4444",
      },
      fontFamily: {
        sans: [
          "Be Vietnam Pro",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        display: ["Be Vietnam Pro", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        soft: "0 10px 40px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
