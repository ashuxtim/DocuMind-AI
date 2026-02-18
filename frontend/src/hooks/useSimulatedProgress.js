import { useState, useEffect } from 'react';

// GLOBAL MEMORY: Stores when each file started uploading.
// This survives tab switching and navigation.
const uploadStartTimes = new Map();

export function useSimulatedProgress(status, filename) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    // 1. IF COMPLETED: Finish immediately
    if (status === 'completed') {
      setProgress(100);
      // Optional: cleanup memory after a delay, handled by component unmounting usually
      return;
    }

    // 2. IF PROCESSING: Calculate progress based on Real Time
    if (status === 'processing' && filename) {
      // Set start time if not exists
      if (!uploadStartTimes.has(filename)) {
        uploadStartTimes.set(filename, Date.now());
      }

      const startTime = uploadStartTimes.get(filename);
      const DURATION_MS = 5 * 60 * 1000; // 5 Minutes target duration

      const timer = setInterval(() => {
        const now = Date.now();
        const elapsed = now - startTime;
        
        // Math: Calculate percentage based on 5 minutes
        // We cap it at 90% so it waits for the backend
        const rawPercent = (elapsed / DURATION_MS) * 90;
        
        // Add a "Fast Start" boost:
        // If we are in the first 5 seconds, fake it to 10% so user sees activity
        const boostedPercent = elapsed < 5000 ? Math.max(rawPercent, 10) : rawPercent;

        setProgress(Math.min(90, Math.round(boostedPercent)));
      }, 1000); // Update every second

      return () => clearInterval(timer);
    }
  }, [status, filename]);

  return progress;
}