/**
 * Smart search with fuzzy matching and ranking
 * Returns documents sorted by relevance
 */
export function smartSearch(documents, searchTerm) {
  if (!searchTerm || !searchTerm.trim()) {
    return documents;
  }

  const term = searchTerm.toLowerCase().trim();
  const words = term.split(/\s+/); // Split search into words

  // Score each document
  const scoredDocs = documents.map(doc => {
    const filename = doc.filename.toLowerCase();
    let score = 0;

    // Exact match (highest priority)
    if (filename === term) {
      score += 1000;
    }

    // Starts with search term
    if (filename.startsWith(term)) {
      score += 500;
    }

    // Contains exact phrase
    if (filename.includes(term)) {
      score += 200;
    }

    // Word-based matching
    words.forEach(word => {
      // Each word starts with search word
      const nameWords = filename.split(/[\s_.-]+/);
      nameWords.forEach((nameWord, index) => {
        if (nameWord.startsWith(word)) {
          score += 100 - (index * 10); // Earlier words get higher score
        }
      });

      // Contains the word anywhere
      if (filename.includes(word)) {
        score += 50;
      }

      // Character proximity (fuzzy)
      const proximity = getCharacterProximity(filename, word);
      score += proximity * 10;
    });

    // Length penalty (prefer shorter matches)
    score -= filename.length * 0.1;

    return { ...doc, searchScore: score };
  });

  // Filter out non-matches and sort by score
  return scoredDocs
    .filter(doc => doc.searchScore > 0)
    .sort((a, b) => b.searchScore - a.searchScore);
}

/**
 * Calculate how closely characters appear together
 */
function getCharacterProximity(text, search) {
  let lastIndex = -1;
  let proximityScore = 0;
  let matches = 0;

  for (const char of search) {
    const index = text.indexOf(char, lastIndex + 1);
    if (index !== -1) {
      matches++;
      if (lastIndex !== -1) {
        const distance = index - lastIndex;
        proximityScore += Math.max(0, 10 - distance); // Closer = higher score
      }
      lastIndex = index;
    }
  }

  return matches === search.length ? proximityScore : 0;
}

/**
 * Highlight matching parts of text
 */
export function highlightMatch(text, searchTerm) {
  if (!searchTerm || !searchTerm.trim()) {
    return text;
  }

  const term = searchTerm.toLowerCase();
  const lowerText = text.toLowerCase();
  const index = lowerText.indexOf(term);

  if (index === -1) {
    // Try word-by-word highlighting
    const words = term.split(/\s+/);
    let result = text;
    words.forEach(word => {
      const wordIndex = result.toLowerCase().indexOf(word);
      if (wordIndex !== -1) {
        result = 
          result.substring(0, wordIndex) +
          `<mark class="bg-primary/20 text-primary">` +
          result.substring(wordIndex, wordIndex + word.length) +
          `</mark>` +
          result.substring(wordIndex + word.length);
      }
    });
    return result;
  }

  return (
    text.substring(0, index) +
    `<mark class="bg-primary/20 text-primary">` +
    text.substring(index, index + term.length) +
    `</mark>` +
    text.substring(index + term.length)
  );
}
