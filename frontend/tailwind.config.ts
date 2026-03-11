import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        harper: {
          bg: "#F8EDE6",
          border: "#e8d9cf",
          accent: "#EC7A72",
          accentHover: "#e06a62",
          secondary: "#2D5E6C",
          text: "#2C2C2C",
        },
      },
    },
  },
  plugins: [],
};
export default config;
