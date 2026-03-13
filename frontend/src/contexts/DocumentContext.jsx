import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getDocuments, uploadDocument, deleteDocument, getTaskStatus, cancelTask } from '@/lib/api';

const DocumentContext = createContext();

export function DocumentProvider({ children }) {
  const [documents, setDocuments] = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadingFiles, setUploadingFiles] = useState(new Map());

  // Fetch documents
  const fetchDocuments = useCallback(async ({ showLoading = true } = {}) => {
    try {
      if (showLoading) {
        setLoading(true);
      }
      const response = await getDocuments();
      const nextDocuments = response.data.documents || [];
      setDocuments(nextDocuments);
      return nextDocuments;
    } catch (error) {
      console.error('Failed to fetch documents:', error);
      return null;
    } finally {
      if (showLoading) {
        setLoading(false);
      }
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

      if (tasksToCheck.length > 0) {
        console.log('[DocumentPolling] Active tasks:', tasksToCheck);
      }
      
      for (const [filename, taskId] of tasksToCheck) {
        try {
          const response = await getTaskStatus(taskId);
          const status = response.data.status;
          console.log('[DocumentPolling] Status response:', { filename, taskId, status, data: response.data });

          if (status === 'SUCCESS' || status === 'FAILURE' || status === 'REVOKED') {
            const nextDocuments = await fetchDocuments({ showLoading: false });
            const latestDocument = nextDocuments?.find((doc) => doc.filename === filename);
            const latestStatus = latestDocument?.status;
            const isTerminalDocumentState = ['completed', 'failed', 'cancelled'].includes(latestStatus);

            if (isTerminalDocumentState) {
              setUploadingFiles(prev => {
                const newMap = new Map(prev);
                newMap.delete(filename);
                return newMap;
              });
            } else {
              console.warn('[DocumentPolling] Celery is terminal but /documents is not updated yet:', {
                filename,
                taskId,
                celeryStatus: status,
                documentStatus: latestStatus ?? 'missing',
              });
            }
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
        console.log('[DocumentUpload] Tracking task:', { filename, taskId: task_id, data: response.data });
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
    await fetchDocuments(); // re-sync with server after delete
  } catch (error) {
    console.error(`Failed to delete ${filename}:`, error);
    alert('Delete failed. Please try again.');
  }
}, [fetchDocuments]);

  const handleCancel = useCallback(async (filename) => {
  try {
    await cancelTask(filename);
    // Full cleanup after cancel — same as delete
    await deleteDocument(filename);
    setUploadingFiles(prev => {
      const newMap = new Map(prev);
      newMap.delete(filename);
      return newMap;
    });
    setDocuments(prev => prev.filter(doc => doc.filename !== filename));
    setSelectedDocs(prev => prev.filter(name => name !== filename));
    await fetchDocuments();
  } catch (error) {
    console.error(`Failed to cancel ${filename}:`, error);
  }
}, [fetchDocuments]);

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
