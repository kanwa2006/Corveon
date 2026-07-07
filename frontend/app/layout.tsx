import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { QueryProvider } from '@/lib/query-provider';
import { ThemeProvider } from '@/lib/theme-provider';

import './globals.css';

export const metadata: Metadata = {
  title: 'Corveon',
  description: 'An evidence-grounded clinical intelligence platform.',
};

const THEME_ANTI_FLASH_SCRIPT = `(function(){try{
  var t=localStorage.getItem('corveon-theme');
  if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);
}catch(e){}})()`;

export default function RootLayout({ children }: { children: ReactNode }): React.JSX.Element {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_ANTI_FLASH_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <QueryProvider>{children}</QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
