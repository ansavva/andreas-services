/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        timeline: {
          line: '#1e293b',
          marker: '#38bdf8'
        }
      },
      boxShadow: {
        glow: '0 20px 45px -20px rgba(56, 189, 248, 0.35)'
      }
    }
  },
  plugins: []
};
