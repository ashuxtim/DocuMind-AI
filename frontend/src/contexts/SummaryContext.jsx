import { createContext, useContext, useState, useCallback } from 'react';
import { summarizeDocument } from '@/lib/api';

const SummaryContext = createContext();

export function SummaryProvider({ children }) {
  const [summaries, setSummaries] = useState(new Map());
  const [loading, setLoading] = useState(new Set());
  const [errors, setErrors] = useState(new Map());

  const generateSummary = useCallback(async (filename) => {
    if (loading.has(filename)) return; // Already loading

    setLoading(prev => new Set(prev).add(filename));
    setErrors(prev => {
      const newMap = new Map(prev);
      newMap.delete(filename);
      return newMap;
    });

    try {
      const response = await summarizeDocument(filename);
      setSummaries(prev => new Map(prev).set(filename, {
        content: response.data.summary,
        timestamp: new Date().toISOString(),
      }));
    } catch (error) {
      console.error(`Failed to summarize ${filename}:`, error);
      setErrors(prev => new Map(prev).set(filename, 
        error.response?.data?.detail || error.message
      ));
    } finally {
      setLoading(prev => {
        const newSet = new Set(prev);
        newSet.delete(filename);
        return newSet;
      });
    }
  }, [loading]);

  const generateMultipleSummaries = useCallback(async (filenames) => {
    // Start all summaries in parallel
    await Promise.all(filenames.map(filename => generateSummary(filename)));
  }, [generateSummary]);

  const clearSummary = useCallback((filename) => {
    setSummaries(prev => {
      const newMap = new Map(prev);
      newMap.delete(filename);
      return newMap;
    });
    setErrors(prev => {
      const newMap = new Map(prev);
      newMap.delete(filename);
      return newMap;
    });
  }, []);

  const clearAllSummaries = useCallback(() => {
    setSummaries(new Map());
    setErrors(new Map());
  }, []);

  const value = {
    summaries,
    loading: Array.from(loading),
    errors,
    generateSummary,
    generateMultipleSummaries,
    clearSummary,
    clearAllSummaries,
  };

  return (
    <SummaryContext.Provider value={value}>
      {children}
    </SummaryContext.Provider>
  );
}

export function useSummaryContext() {
  const context = useContext(SummaryContext);
  if (!context) {
    throw new Error('useSummaryContext must be used within SummaryProvider');
  }
  return context;
}
