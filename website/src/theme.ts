import { useEffect, useState } from 'react';
import { Mode, applyMode } from '@cloudscape-design/global-styles';

export type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'dstack-theme';

// Defaults to light; remembers the visitor's explicit choice.
function getInitialTheme(): ThemeMode {
  return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
}

// Tracks light/dark mode and applies it to the Cloudscape global styles + the document.
export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    root.dataset.theme = theme;
    body.classList.add('awsui-visual-refresh');
    applyMode(theme === 'dark' ? Mode.Dark : Mode.Light);
  }, [theme]);

  const toggleTheme = () =>
    setTheme(current => {
      const next = current === 'light' ? 'dark' : 'light';
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });

  return { theme, toggleTheme };
}
