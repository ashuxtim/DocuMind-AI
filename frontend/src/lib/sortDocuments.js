export function sortDocuments(documents, sortBy) {
  const sorted = [...documents];
  
  switch (sortBy) {
    case 'name-asc':
      return sorted.sort((a, b) => 
        a.filename.localeCompare(b.filename)
      );
    
    case 'name-desc':
      return sorted.sort((a, b) => 
        b.filename.localeCompare(a.filename)
      );
    
    case 'date-desc':
      return sorted.sort((a, b) => {
        const dateA = a.uploaded_at || a.completed_at || '0';
        const dateB = b.uploaded_at || b.completed_at || '0';
        return dateB.localeCompare(dateA);
      });
    
    case 'date-asc':
      return sorted.sort((a, b) => {
        const dateA = a.uploaded_at || a.completed_at || '0';
        const dateB = b.uploaded_at || b.completed_at || '0';
        return dateA.localeCompare(dateB);
      });
    
    case 'size-desc':
      return sorted.sort((a, b) => (b.size || 0) - (a.size || 0));
    
    case 'size-asc':
      return sorted.sort((a, b) => (a.size || 0) - (b.size || 0));
    
    default:
      return sorted;
  }
}
