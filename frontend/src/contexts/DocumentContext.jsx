import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getDocuments, uploadDocument, deleteDocument, getTaskStatus, cancelTask } from '@/lib/api';

const DocumentContext = createContext();

export function DocumentProvider({ children }) {
  const [documents, setDocuments] = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadingFiles, setUploadingFiles] = useState(new Map());

  // Fetch documents
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

  // Initial load
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Poll for upload status
  useEffect(() => {
    const pollInterval = setInterval(async () => {
      const tasksToCheck = Array.from(uploadingFiles.entries());
      
      for (const [filename, taskId] of tasksToCheck) {
        try {
          const response = await getTaskStatus(taskId);
          const status = response.data.status;

          if (status === 'SUCCESS' || status === 'FAILURE') {
            setUploadingFiles(prev => {
              const newMap = new Map(prev);
              newMap.delete(filename);
              return newMap;
            });
            fetchDocuments();
          }
        } catch (error) {
          console.error(`Failed to check status for ${filename}:`, error);
        }
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [uploadingFiles, fetchDocuments]);

  const handleUpload = useCallback(async (files) => {
    const fileArray = Array.isArray(files) ? files : [files];
    
    for (const file of fileArray) {
      try {
        const response = await uploadDocument(file);
        const { task_id, filename } = response.data;
        setUploadingFiles(prev => new Map(prev).set(filename, task_id));
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        alert(`Upload failed: ${error.response?.data?.detail || error.message}`);
      }
    }
  }, []);

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

  const handleCancel = useCallback(async (filename) => {
    // Find the task_id for this filename
    const taskId = Array.from(uploadingFiles.entries())
      .find(([name]) => name === filename)?.[1];
    
    if (!taskId) {
      console.warn('No task ID found for', filename);
      return;
    }

    try {
      // Use the centralized API wrapper instead of hardcoded fetch
      await cancelTask(taskId);
      
      // Remove from uploading list
      setUploadingFiles(prev => {
        const newMap = new Map(prev);
        newMap.delete(filename);
        return newMap;
      });
      
      console.log(`Cancelled: ${filename}`);
    } catch (error) {
      console.error(`Failed to cancel ${filename}:`, error);
    }
  }, [uploadingFiles]);

  const toggleSelection = useCallback((filename) => {
    setSelectedDocs(prev => {
      if (prev.includes(filename)) {
        return prev.filter(name => name !== filename);
      } else {
        return [...prev, filename];
      }
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedDocs([]);
  }, []);

  const selectAll = useCallback(() => {
    const completedDocs = documents
      .filter(doc => doc.status === 'completed')
      .map(doc => doc.filename);
    setSelectedDocs(completedDocs);
  }, [documents]);

  const value = {
    documents,
    selectedDocs,
    loading,
    uploadingFiles: Array.from(uploadingFiles.keys()),
    handleUpload,
    handleDelete,
    handleCancel,
    toggleSelection,
    clearSelection,
    selectAll,
    refreshDocuments: fetchDocuments,
  };

  return (
    <DocumentContext.Provider value={value}>
      {children}
    </DocumentContext.Provider>
  );
}

export function useDocumentContext() {
  const context = useContext(DocumentContext);
  if (!context) {
    throw new Error('useDocumentContext must be used within DocumentProvider');
  }
  return context;
}