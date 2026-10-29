/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        void: '#07070d',
        panel: '#111018',
        hairline: '#211f2c',
        ink: '#e7e4ef',
        'ink-muted': '#6f6b80',
        violet: '#7c6aff',
        phosphor: '#4ee6b8',
        amber: '#ffb454',
        critical: '#ff5d5d',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
}
