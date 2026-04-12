/** @type {import('tailwindcss').Config} */

/**
 * Tailwind configuration for ai-roundtable v2.
 *
 * Design system variables (from CLAUDE.md):
 *   --color-bg:             #0d0d0d   app background
 *   --color-surface:        #1e1e1e   cards, bubbles, inputs — NEVER use bg for inputs
 *   --color-border:         #2a2a2a   borders at rest
 *   --color-border-focus:   #E8712A   borders on focus
 *   --color-text-primary:   #e8e8e8
 *   --color-text-secondary: #888888
 *
 * Model colors:
 *   --color-claude:         #E8712A   orange
 *   --color-gemini:         #4285F4   Google blue
 *   --color-gpt:            #10A37F   OpenAI green
 *   --color-perplexity:     #8B5CF6   purple
 *   --color-you:            #2a2a2a   dark — user bubbles
 */

module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d0d0d",
        surface: "#1e1e1e",
        border: "#2a2a2a",
        "border-focus": "#E8712A",
        "text-primary": "#e8e8e8",
        "text-secondary": "#888888",
        claude: "#E8712A",
        gemini: "#4285F4",
        gpt: "#10A37F",
        perplexity: "#8B5CF6",
        you: "#2a2a2a",
      },
    },
  },
  plugins: [],
};
