/** @type {import('tailwindcss').Config} */

/**
 * Tailwind — ai-roundtable design system.
 * Orange (#E8712A) is Claude-only (bubbles, labels, Claude stream pulse).
 * UI chrome uses neutral accent-ui grays.
 */

module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d0d0d",
        surface: "#1e1e1e",
        border: "#2a2a2a",
        "border-focus": "#6B6B6B",
        "accent-ui": "#6B6B6B",
        "accent-ui-light": "#888888",
        "text-primary": "#e8e8e8",
        "text-secondary": "#888888",
        claude: "#E8712A",
        gemini: "#4285F4",
        gpt: "#10A37F",
        perplexity: "#20808D",
        you: "#2a2a2a",
      },
      caretColor: {
        chrome: "#e8e8e8",
      },
    },
  },
  plugins: [],
};
