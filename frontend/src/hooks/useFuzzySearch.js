import { useMemo } from 'react';

/**
 * Pure utility hook for fuzzy searching an array of objects.
 *
 * @param {Array}  items  — array of objects to search
 * @param {string} query  — search string (space-separated words)
 * @param {string} key    — which field on each object to match against
 * @returns {Array} filtered & relevance-sorted subset of items
 */
export default function useFuzzySearch(items, query, key) {
  return useMemo(() => {
    const trimmed = (query || '').trim();
    if (!trimmed) return items;

    const lowerQuery = trimmed.toLowerCase();
    const words = lowerQuery.split(/\s+/).filter(Boolean);

    // Score each item — higher is better, -1 means no match
    const scored = items.map((item) => {
      const value = (item[key] || '').toLowerCase();

      // Every word must appear somewhere in the value
      const allMatch = words.every((w) => value.includes(w));
      if (!allMatch) return null;

      // Scoring:
      //   3 — exact full-query substring match  (best)
      //   2 — starts with the full query
      //   1 — fuzzy multi-word match             (baseline)
      let score = 1;
      if (value.includes(lowerQuery)) {
        score = value.startsWith(lowerQuery) ? 3 : 2;
      }

      return { item, score };
    });

    return scored
      .filter(Boolean)
      .sort((a, b) => b.score - a.score)
      .map((entry) => entry.item);
  }, [items, query, key]);
}
