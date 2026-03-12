import { useEffect, useRef } from 'react';

export function usePolling(callback, interval = 2000, enabled = true) {
  const savedCallback = useRef();

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return;

    function tick() {
      savedCallback.current?.();
    }

    const id = setInterval(tick, interval);
    return () => clearInterval(id);
  }, [interval, enabled]);
}
