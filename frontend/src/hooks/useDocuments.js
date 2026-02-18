import { useState, useEffect, useCallback } from 'react';
import { getDocuments, uploadDocument, deleteDocument, getTaskStatus } from '@/lib/api';

export function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadingFiles, setUploadingFiles] = useState(new Map());

  // Fetch documents from backend
  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      const response = await getDocuments();
      setDocuments(response.data.documents || []);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Poll task status for uploading files
  useEffect(() => {
    const pollInterval = setInterval(async () => {
      const tasksToCheck = Array.from(uploadingFiles.entries());
      
      for (const [filename, taskId] of tasksToCheck) {
        try {
          const response = await getTaskStatus(taskId);
          const status = response.data.status;

          if (status === 'SUCCESS' || status === 'FAILURE') {
            // Remove from uploading list
            setUploadingFiles(prev => {
              const newMap = new Map(prev);
              newMap.delete(filename);
              return newMap;
            });
            
            // Refresh document list
            fetchDocuments();
          }
        } catch (error) {
          console.error(`Failed to check status for ${filename}:`, error);
        }
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [uploadingFiles, fetchDocuments]);

  // Upload handler
  const handleUpload = useCallback(async (files) => {
    const fileArray = Array.isArray(files) ? files : [files];
    
    for (const file of fileArray) {
      try {
        const response = await uploadDocument(file);
        const { task_id, filename } = response.data;
        
        // Track uploading file
        setUploadingFiles(prev => new Map(prev).set(filename, task_id));
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        alert(`Upload failed: ${error.response?.data?.detail || error.message}`);
      }
    }
  }, []);

  // Delete handler
  const handleDelete = useCallback(async (filename) => {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) {
      return;
    }

    try {
      await deleteDocument(filename);
      setDocuments(prev => prev.filter(doc => doc.filename !== filename));
      setSelectedDocs(prev => prev.filter(name => name !== filename));
    } catch (error) {
      console.error(`Failed to delete ${filename}:`, error);
      alert('Delete failed. Please try again.');
    }
  }, []);

  // Toggle document selection
  const toggleSelection = useCallback((filename) => {
    setSelectedDocs(prev => {
      if (prev.includes(filename)) {
        return prev.filter(name => name !== filename);
      } else {
        return [...prev, filename];
      }
    });
  }, []);

  // Clear all selections
  const clearSelection = useCallback(() => {
    setSelectedDocs([]);
  }, []);

  // Select all documents
  const selectAll = useCallback(() => {
    const completedDocs = documents
      .filter(doc => doc.status === 'completed')
      .map(doc => doc.filename);
    setSelectedDocs(completedDocs);
  }, [documents]);

  return {
    documents,
    selectedDocs,
    loading,
    uploadingFiles: Array.from(uploadingFiles.keys()),
    handleUpload,
    handleDelete,
    toggleSelection,
    clearSelection,
    selectAll,
    refreshDocuments: fetchDocuments,
  };
}
