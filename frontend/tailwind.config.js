/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        // GitNexus Dark Theme Obsidian Colors
        void: "#06060a",
        deep: "#0a0a10",
        surface: "#101018",
        elevated: "#16161f",
        hover: "#1c1c28",
        "border-subtle": "#1e1e2a",
        "border-default": "#2a2a3a",
        "text-primary": "#e4e4ed",
        "text-secondary": "#8888a0",
        "text-muted": "#5a5a70",
        "accent-purple": "#7c3aed",
        "accent-purple-dim": "#5b21b6",
        // Entity node type colors
        "node-person": "#34d399",
        "node-organization": "#fbbf24",
        "node-statute": "#a78bfa",
        "node-date": "#22d3ee",
        "node-document": "#f472b6",
        "node-entity": "#94a3b8",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      boxShadow: {
        glow: "0 0 20px rgba(124, 58, 237, 0.4)",
        "glow-soft": "0 0 40px rgba(124, 58, 237, 0.15)",
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        shimmer: {
          '0%': { backgroundPosition: '0 0' },
          '100%': { backgroundPosition: '1rem 1rem' }
        },
        breathe: {
          '0%, 100%': { borderColor: '#2a2a3a', boxShadow: '0 0 0 0 rgba(124, 58, 237, 0.3)' },
          '50%': { borderColor: '#7c3aed', boxShadow: '0 0 40px 10px rgba(124, 58, 237, 0.3)' },
        },
        'pulse-glow': {
          '0%, 100%': { transform: 'scale(1)', boxShadow: '0 0 40px rgba(124, 58, 237, 0.4)' },
          '50%': { transform: 'scale(1.05)', boxShadow: '0 0 80px rgba(124, 58, 237, 0.6)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(20px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        shimmer: "shimmer 1s linear infinite",
        breathe: "breathe 3s ease-in-out infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "slide-in": "slide-in 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "slide-up": "slide-up 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "fade-in": "fade-in 0.3s ease-out",
      },
    },
  },
  plugins: [],
}