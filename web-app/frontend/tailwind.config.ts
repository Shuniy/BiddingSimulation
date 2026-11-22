import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#172026",
        paper: "#f7f7f4",
        line: "#d8ddd8",
        accent: "#2f7d6d",
        ember: "#b8563b",
      },
      boxShadow: {
        panel: "0 12px 36px rgba(23, 32, 38, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;

