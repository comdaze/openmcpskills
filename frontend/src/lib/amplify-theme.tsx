/**
 * Amplify Theme Provider (optional - for Amplify UI components)
 * If not using Amplify, this provides a pass-through wrapper
 */

import { ReactNode } from 'react';

export const amplifyTheme = {};

interface ThemeProviderProps {
  theme?: unknown;
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  return <>{children}</>;
}
