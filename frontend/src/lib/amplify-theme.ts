import { createTheme, ThemeProvider } from '@aws-amplify/ui-react';

// Shadcn uses the zinc color palette as base
export const amplifyTheme = createTheme({
  name: 'shadcn-theme',
  tokens: {
    fonts: {
      default: {
        variable: { value: "'Inter', system-ui, sans-serif" },
        static: { value: "'Inter', system-ui, sans-serif" }
      },
    },
    fontSizes: {
      small: { value: '0.75rem' },
      medium: { value: '0.875rem' }, // 14px - matches Tailwind's text-sm
      large: { value: '1rem' },
      xl: { value: '1.125rem' },
      xxl: { value: '1.25rem' },
      xxxl: { value: '1.5rem' },
    },
    colors: {
      background: {
        primary: { value: '#ffffff' }, // Light mode background
        secondary: { value: '#f4f4f5' }, // zinc-100
      },
      font: {
        interactive: { value: '#18181b' }, // zinc-900
        primary: { value: '#18181b' }, // zinc-900
        secondary: { value: '#71717a' }, // zinc-500
      },
      brand: {
        primary: {
          10: { value: '#27272a' }, // zinc-800
          20: { value: '#27272a' }, // zinc-800
          40: { value: '#27272a' }, // zinc-800
          60: { value: '#27272a' }, // zinc-800
          80: { value: '#27272a' }, // zinc-800
          90: { value: '#27272a' }, // zinc-800
          100: { value: '#27272a' }, // zinc-800
        },
      },
      border: {
        primary: { value: '#e4e4e7' }, // zinc-200
        secondary: { value: '#e4e4e7' }, // zinc-200
        tertiary: { value: '#e4e4e7' }, // zinc-200
      },
      overlay: {
        10: { value: '#ffffff' }, // White
        20: { value: '#ffffff' }, // White
        30: { value: '#ffffff' }, // White
      },
      label: {
        color: { value: '#18181b' }, // zinc-900 - matching text color
      },
    },
    components: {
      button: {
        fontWeight: { value: 'normal' },
        primary: {
          backgroundColor: { value: '#27272a' }, // zinc-800
          color: { value: '#ffffff' }, // White
          borderColor: { value: '#27272a' }, // zinc-800
          _hover: {
            backgroundColor: { value: '#3f3f46' }, // zinc-700
          },
          _active: {
            backgroundColor: { value: '#52525b' }, // zinc-600
          },
          _focus: {
            backgroundColor: { value: '#3f3f46' }, // zinc-700
            borderColor: { value: '#a1a1aa' }, // zinc-400
          },
          _disabled: {
            backgroundColor: { value: '#71717a' }, // zinc-500
          },
        },
        link: {
          color: { value: '#27272a' }, // zinc-800
          backgroundColor: { value: 'transparent' },
          borderColor: { value: 'transparent' },
          _hover: {
            color: { value: '#3f3f46' }, // zinc-700
            backgroundColor: { value: 'transparent' },
            borderColor: { value: 'transparent' },
          },
          _active: {
            color: { value: '#18181b' }, // zinc-900
            backgroundColor: { value: 'transparent' },
            borderColor: { value: 'transparent' },
          },
          _focus: {
            color: { value: '#3f3f46' }, // zinc-700
            backgroundColor: { value: 'transparent' },
            borderColor: { value: '#a1a1aa' }, // zinc-400
          },
          _disabled: {
            color: { value: '#71717a' }, // zinc-500
            backgroundColor: { value: 'transparent' },
          },
        },
      },
      fieldcontrol: {
        borderColor: { value: 'var(--input, #e4e4e7)' }, // Use CSS variable with fallback to zinc-200
        borderWidth: { value: '1px' },
        borderRadius: { value: 'var(--radius, 0.375rem)' },
      },
      authenticator: {
        router: {
          borderWidth: { value: '0' },
          boxShadow: { value: 'none' },
          borderStyle: { value: 'none' }, // zinc-200
        },
      },
      tabs: {
        borderStyle: { value: 'none' },
        item: {
          borderColor: { value: '#e4e4e7' }, // zinc-200
          borderWidth: { value: '0' },
          _active: {
            color: { value: '#27272a' }, // zinc-800
            borderColor: { value: '#27272a' }, // zinc-800
          },
          _hover: {
            color: { value: '#3f3f46' }, // zinc-700
          },
        },
      },
      field: {
        label: {
          color: { value: '#18181b' }, // zinc-900 - matching text color
        },
      },
    },
  },
  overrides: [
    {
      colorMode: 'dark',
      tokens: {
        colors: {
          background: {
            primary: { value: '#18181b' }, // zinc-900
            secondary: { value: '#27272a' }, // zinc-800
          },
          font: {
            interactive: { value: '#ffffff' }, // White
            primary: { value: '#ffffff' }, // White
            secondary: { value: '#a1a1aa' }, // zinc-400
          },
          brand: {
            primary: {
              10: { value: '#ffffff' }, // White
              20: { value: '#ffffff' }, // White
              40: { value: '#ffffff' }, // White
              60: { value: '#ffffff' }, // White
              80: { value: '#ffffff' }, // White
              90: { value: '#ffffff' }, // White
              100: { value: '#ffffff' }, // White
            },
          },
          border: {
            primary: { value: '#27272a' }, // zinc-800
            secondary: { value: '#27272a' }, // zinc-800
            tertiary: { value: '#27272a' }, // zinc-800
          },
          overlay: {
            10: { value: '#18181b' }, // zinc-900
            20: { value: '#18181b' }, // zinc-900
            30: { value: '#18181b' }, // zinc-900
          },
        },
        components: {
          card: {
            boxShadow: { value: 'none' },
            borderWidth: { value: '0' },
          },
          button: {
            link: {
              color: { value: '#ffffff' }, // White for dark mode
              backgroundColor: { value: 'transparent' },
              _hover: {
                color: { value: '#e4e4e7' }, // zinc-200 for dark mode
                backgroundColor: { value: 'transparent' },
              },
              _active: {
                color: { value: '#f4f4f5' }, // zinc-100 for dark mode
                backgroundColor: { value: 'transparent' },
              },
              _focus: {
                color: { value: '#e4e4e7' }, // zinc-200 for dark mode
                backgroundColor: { value: 'transparent' },
                borderColor: { value: '#71717a' }, // zinc-500 for dark mode
              },
            },
            primary: {
              _focus: {
                backgroundColor: { value: '#3f3f46' }, // zinc-700
                borderColor: { value: '#71717a' }, // zinc-500
              },
            },
          },
          field: {
            label: {
              color: { value: '#ffffff' }, // White - matching dark mode text color
            },
          },
          fieldcontrol: {
            borderColor: { value: 'var(--input, #27272a)' }, // Use CSS variable with fallback to zinc-800
          },
        },
      },
    },
  ],
});

// Export the ThemeProvider for convenience
export { ThemeProvider }; 