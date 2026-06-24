import { useState, useEffect } from 'react';

/**
 * Debounce a value with a specified delay.
 * Returns the debounced value that updates after the delay.
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
