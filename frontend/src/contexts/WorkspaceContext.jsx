import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import {
  getDocuments,
  uploadDocument as apiUpload,
  deleteDocument as apiDelete,
  queryKnowledgeBase,
  summarizeDocument,
} from '@/lib/api';

// ─────────────────────────────────────────────────────────
// Context
// ─────────────────────────────────────────────────────────
const WorkspaceContext = createContext(null);

// ─────────────────────────────────────────────────────────
// Provider
// ─────────────────────────────────────────────────────────
export function WorkspaceProvider({ children }) {
  // ═══════════════════════════════════════════════════════
  // DOCUMENTS
  // ═══════════════════════════════════════════════════════
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [uploadingFiles, setUploadingFiles] = useState([]); // filenames currently processing

  const fetchDocuments = useCallback(async () => {
    try {
      setDocsLoading(true);
      const response = await getDocuments();
      const docs = response.data.documents || [];
      setDocuments(docs);
      return docs;
    } catch (error) {
      console.error('[WorkspaceContext] fetchDocuments failed:', error);
      return [];
    } finally {
      setDocsLoading(false);
    }
  }, []);

  // Poll for processing documents until they reach a terminal state
  useEffect(() => {
    if (uploadingFiles.length === 0) return;

    const interval = setInterval(async () => {
      const freshDocs = await getDocuments()
        .then((r) => r.data.documents || [])
        .catch(() => null);

      if (!freshDocs) return;

      setDocuments(freshDocs);

      setUploadingFiles((prev) => {
        const stillProcessing = prev.filter((filename) => {
          const doc = freshDocs.find((d) => d.filename === filename);
          // Keep polling if doc not found yet or still processing
          if (!doc) return true;
          return !['completed', 'failed', 'cancelled'].includes(doc.status);
        });
        return stillProcessing.length === prev.length ? prev : stillProcessing;
      });
    }, 2000);

    return () => clearInterval(interval);
  }, [uploadingFiles]);

  const uploadDocument = useCallback(async (file) => {
    try {
      const response = await apiUpload(file);
      const { filename } = response.data;
      console.log('[WorkspaceContext] Upload started:', filename);
      setUploadingFiles((prev) => [...prev, filename]);
    } catch (error) {
      console.error('[WorkspaceContext] Upload failed:', error);
      throw error;
    }
  }, []);

  const deleteDocument = useCallback(async (filename) => {
    try {
      await apiDelete(filename);
      setDocuments((prev) => prev.filter((d) => d.filename !== filename));
      setSelectedDocs((prev) => prev.filter((f) => f !== filename));
    } catch (error) {
      console.error('[WorkspaceContext] Delete failed:', error);
      throw error;
    }
  }, []);

  // ═══════════════════════════════════════════════════════
  // SELECTION
  // ═══════════════════════════════════════════════════════
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [activeDoc, setActiveDocState] = useState(null);

  const toggleSelection = useCallback((filename) => {
    setSelectedDocs((prev) =>
      prev.includes(filename)
        ? prev.filter((f) => f !== filename)
        : [...prev, filename]
    );
  }, []);

  const setActiveDoc = useCallback((filename) => {
    setActiveDocState(filename);
  }, []);

  const clearActiveDoc = useCallback(() => {
    setActiveDocState(null);
  }, []);

  // ═══════════════════════════════════════════════════════
  // CHAT
  // ═══════════════════════════════════════════════════════
  const [messages, setMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);

  // Reset messages whenever activeDoc changes
  useEffect(() => {
    setMessages([]);
  }, [activeDoc]);

  const sendMessage = useCallback(
    async (question) => {
      if (!question.trim()) return;

      const userMessage = {
        id: Date.now(),
        role: 'user',
        content: question,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);
      setChatLoading(true);

      try {
        const history = messages.slice(-6).map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const payload = {
          question,
          history,
          selected_docs: activeDoc
            ? [activeDoc, ...selectedDocs.filter((f) => f !== activeDoc)]
            : selectedDocs,
        };

        const response = await queryKnowledgeBase(payload);
        const data = response.data || response;
        const answerText = data.answer || data.result || 'No answer provided.';

        const aiMessage = {
          id: Date.now() + 1,
          role: 'assistant',
          content: answerText,
          sources: data.context_used || data.sources || [],
          confidence: data.confidence || 0,
          model: data.model || 'unknown',
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, aiMessage]);
      } catch (error) {
        console.error('[WorkspaceContext] Chat error:', error);
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: 'assistant',
            content: `Error: ${error.message || 'Failed to get response.'}`,
            timestamp: new Date().toISOString(),
            isError: true,
          },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [messages, activeDoc, selectedDocs]
  );

  const clearChat = useCallback(() => setMessages([]), []);

  // ═══════════════════════════════════════════════════════
  // SUMMARY
  // ═══════════════════════════════════════════════════════
  const [summaryCache] = useState(() => new Map());
  const [summaryLoadingSet, setSummaryLoadingSet] = useState(() => new Set());
  const summaryInFlight = useRef(new Set());
  const pdfViewerRef = useRef(null);

  const isSummaryLoading = useCallback(
    (filename) => summaryLoadingSet.has(filename),
    [summaryLoadingSet]
  );

  const generateSummary = useCallback(
    async (filename) => {
      // Avoid duplicate concurrent requests for the same file
      if (summaryInFlight.current.has(filename)) return;

      // Skip if we already have a successful summary in memory
      const existing = summaryCache.get(filename);
      if (existing && existing.content && !existing.error) return;

      // --- FIX 1: Check localStorage before hitting the API ---
      try {
        const stored = localStorage.getItem(`documind_summary_${filename}`);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed && parsed.content) {
            summaryCache.set(filename, parsed);
            return;
          }
        }
      } catch (_) {
        // localStorage unavailable or corrupt — proceed with API call
      }

      summaryInFlight.current.add(filename);
      setSummaryLoadingSet((prev) => new Set(prev).add(filename));

      try {
        const response = await summarizeDocument(filename);
        const entry = {
          content: response.data.summary,
          timestamp: new Date().toISOString(),
        };

        // Write to in-memory cache
        summaryCache.set(filename, entry);

        // Write to localStorage for persistence across refresh
        try {
          localStorage.setItem(`documind_summary_${filename}`, JSON.stringify(entry));
        } catch (_) {
          // Storage full or disabled — degrade gracefully
        }
      } catch (error) {
        console.error('[WorkspaceContext] Summary failed:', filename, error);

        // --- FIX 3: Write error entry to in-memory cache only (not localStorage) ---
        summaryCache.set(filename, {
          error: true,
          message: error?.response?.data?.detail || 'Summary generation failed',
          timestamp: new Date().toISOString(),
        });
      } finally {
        summaryInFlight.current.delete(filename);
        setSummaryLoadingSet((prev) => {
          const next = new Set(prev);
          next.delete(filename);
          return next;
        });
      }
    },
    [summaryCache]
  );

  const getSummary = useCallback(
    (filename) => summaryCache.get(filename) || null,
    [summaryCache]
  );

  const clearSummary = useCallback(
    (filename) => {
      summaryCache.delete(filename);
      try {
        localStorage.removeItem(`documind_summary_${filename}`);
      } catch (_) {
        // localStorage unavailable — ignore
      }
    },
    [summaryCache]
  );

  // Auto-generate summary when activeDoc changes
  // Re-triggers on error entries so user gets a fresh attempt on re-open
  useEffect(() => {
    if (!activeDoc) return;
    const cached = summaryCache.get(activeDoc);
    if (!cached || cached.error) {
      generateSummary(activeDoc);
    }
  }, [activeDoc, summaryCache, generateSummary]);

  // ═══════════════════════════════════════════════════════
  // ON MOUNT — fetch documents
  // ═══════════════════════════════════════════════════════
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // ═══════════════════════════════════════════════════════
  // CONTEXT VALUE
  // ═══════════════════════════════════════════════════════
  const value = {
    // Documents
    documents,
    docsLoading,
    uploadingFiles,
    fetchDocuments,
    uploadDocument,
    deleteDocument,

    // Selection
    selectedDocs,
    activeDoc,
    toggleSelection,
    setActiveDoc,
    clearActiveDoc,

    // Chat
    messages,
    chatLoading,
    sendMessage,
    clearChat,

    // Summary
    summaryCache,
    isSummaryLoading,
    generateSummary,
    getSummary,
    clearSummary,

    // PDF viewer
    pdfViewerRef,
  };

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

// ─────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────
export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspace() must be used within a <WorkspaceProvider>');
  }
  return context;
}
