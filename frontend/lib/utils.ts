import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

const RELATIVE_TIME_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
];

const relativeTimeFormatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

export function formatRelativeTime(isoDate: string): string {
  const seconds = (new Date(isoDate).getTime() - Date.now()) / 1000;
  for (const [unit, secondsInUnit] of RELATIVE_TIME_UNITS) {
    if (Math.abs(seconds) >= secondsInUnit) {
      return relativeTimeFormatter.format(Math.round(seconds / secondsInUnit), unit);
    }
  }
  return relativeTimeFormatter.format(Math.round(seconds), 'second');
}
