import { useEffect } from 'react';

export function useKeyboard(shortcuts) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      // Check for Cmd (Mac) or Ctrl (Windows/Linux)
      const isCmdOrCtrl = event.metaKey || event.ctrlKey;
      
      shortcuts.forEach(({ key, ctrlKey, callback }) => {
        if (ctrlKey && isCmdOrCtrl && event.key === key) {
          event.preventDefault();
          callback();
        } else if (!ctrlKey && event.key === key && !event.metaKey && !event.ctrlKey) {
          callback();
        }
      });
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);
}
