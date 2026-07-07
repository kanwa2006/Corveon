import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { THEME_STORAGE_KEY, ThemeProvider, useTheme } from '@/lib/theme-provider';

function ThemeProbe(): React.JSX.Element {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme-value">{theme}</span>
      <button onClick={() => setTheme('dark')}>dark</button>
      <button onClick={() => setTheme('light')}>light</button>
    </div>
  );
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to system when nothing is persisted', () => {
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('theme-value')).toHaveTextContent('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('reads a persisted theme on initial render', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('theme-value')).toHaveTextContent('dark');
  });

  it('setTheme updates state, localStorage, and the DOM attribute', () => {
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByText('dark'));

    expect(screen.getByTestId('theme-value')).toHaveTextContent('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('switching back to light removes the dark attribute correctly', () => {
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByText('dark'));
    fireEvent.click(screen.getByText('light'));

    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });
});
