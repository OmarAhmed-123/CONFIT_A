/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        confit: {
          navy: {
            DEFAULT: '#1B1F3B',
            50: '#F0F2F8',
            100: '#E1E5F2',
            200: '#C2CBE5',
            300: '#94A3D0',
            400: '#5F74B4',
            500: '#3D5296',
            600: '#2A3C78',
            700: '#1B1F3B',
            800: '#13162C',
            900: '#0C0E1E',
          },
          gold: {
            DEFAULT: '#B8935A',
            50: '#FDF8EE',
            100: '#F8EECF',
            200: '#EED9A0',
            300: '#E2BF70',
            400: '#D4AF37',
            500: '#B8935A',
            600: '#9C7844',
            700: '#7E5E33',
            800: '#644827',
            900: '#523A20',
          },
          cream: '#FAF9F6',
          charcoal: '#1E293B',
          muted: '#777777',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        arabic: ['Cairo', 'Tajawal', 'IBM Plex Sans Arabic', 'system-ui', 'sans-serif'],
        serif: ['Playfair Display', 'Georgia', 'serif'],
      },
      /* Motion token (home pass 3): ONE luxury easing curve for hover /
         reveal transitions instead of ad-hoc default easings per call site.
         cubic-bezier(0.25, 1, 0.5, 1) = fast start, long soft landing. */
      transitionTimingFunction: {
        luxury: 'cubic-bezier(0.25, 1, 0.5, 1)',
      },
      /* Shadow token (B01 pass): Tailwind v3's built-in scale is
         sm/DEFAULT/md/lg/xl/2xl/inner/none — it has NO `xs` and NO `2xs`,
         which are v4 names. 106 call sites across src/ were already written
         against `shadow-2xs` (80) and `shadow-xs` (26) and therefore emitted
         NO CSS at all: cards that read as flat were never given the hairline
         depth their call site asked for. Verified by requiring
         `tailwindcss/defaultTheme` from a clean 3.4.14 install rather than by
         assumption.

         Declaring the two missing steps here fixes every call site at once
         instead of rewriting 106 class strings — and keeps the scale
         monotonic, so `2xs < xs < sm < (default) < md …` still means
         something. Values follow the existing --surface-raised-shadow
         language in styles/index.css: low blur, negative spread, navy tint. */
      boxShadow: {
        '2xs': '0 1px 2px -1px rgb(27 31 59 / 0.06)',
        'xs': '0 2px 4px -2px rgb(27 31 59 / 0.08)',
      },
    },
  },
  plugins: [],
}
