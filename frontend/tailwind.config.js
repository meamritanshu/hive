/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        hive: {
          50: "#fef9ec",
          100: "#fdf0c8",
          200: "#fbe08d",
          300: "#f9c84d",
          400: "#f7b525",
          500: "#f19a0c",
          600: "#d57507",
          700: "#b1530a",
          800: "#90410e",
          900: "#76360f",
          950: "#441b04",
        },
        surface: {
          DEFAULT: "#0f1117",
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5d8e2",
          300: "#b0b6c8",
          400: "#858ea9",
          500: "#66708f",
          600: "#515a76",
          700: "#424960",
          800: "#393f51",
          900: "#1a1d2e",
          950: "#0f1117",
        },
      },
    },
  },
  plugins: [],
};
