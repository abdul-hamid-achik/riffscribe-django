/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './transcriber/templates/**/*.html',
    './transcriber/static/transcriber/js/**/*.js',
    './node_modules/crispy-tailwind/**/*.html',
    './node_modules/crispy-tailwind/**/*.js',
    './node_modules/crispy-tailwind/**/*.py',
  ],
  theme: {
    extend: {
      fontFamily: {
        'display': ['Playfair Display', 'Georgia', 'serif'],
        'headline': ['Crimson Text', 'Georgia', 'serif'], 
        'body': ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // NYT-inspired colors
        'nyt-black': '#121212',
        'nyt-gray-dark': '#333333',
        'nyt-gray-medium': '#666666',
        'nyt-gray-light': '#999999',
        'nyt-border': '#e6e6e6',
        
        // Sheet music colors
        'sheet-cream': '#faf8f3',
        'sheet-ivory': '#f8f6f0',
        
        // Musical colors
        'musical-gold': '#c9a96e',
        'musical-treble': '#8b4513',
        'musical-staff': '#2c2c2c',
        'musical-note': '#1a1a1a',
        
        // Status colors
        'primary-blue': '#326891',
        'hover-blue': '#2c5aa0',
        'success-green': '#047857',
        'warning-amber': '#d97706',
        'error-red': '#dc2626',
      },
      backgroundImage: {
        'staff-lines': `repeating-linear-gradient(
          transparent,
          transparent 19px,
          #2c2c2c 19px,
          #2c2c2c 20px,
          transparent 20px,
          transparent 24px,
          #2c2c2c 24px,
          #2c2c2c 25px,
          transparent 25px,
          transparent 29px,
          #2c2c2c 29px,
          #2c2c2c 30px,
          transparent 30px,
          transparent 34px,
          #2c2c2c 34px,
          #2c2c2c 35px,
          transparent 35px,
          transparent 39px,
          #2c2c2c 39px,
          #2c2c2c 40px
        )`,
      }
    },
  },
  plugins: [],
}