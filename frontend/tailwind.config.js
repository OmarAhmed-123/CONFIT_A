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
      }
    },
  },
  plugins: [],
}
