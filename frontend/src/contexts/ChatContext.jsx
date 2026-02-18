import { createContext, useContext, useState, useCallback } from 'react';
import { queryKnowledgeBase } from '@/lib/api';

const ChatContext = createContext();

export function ChatProvider({ children }) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeRequest, setActiveRequest] = useState(null);

  const sendMessage = useCallback(async (question, selectedDocs) => {
    if (!question.trim() || selectedDocs.length === 0) return;

    // 1. Add User Message
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: question,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);

    setIsLoading(true);
    setActiveRequest({ question, docs: selectedDocs });

    try {
      // 2. Sanitize History (Strip complex objects)
      const cleanHistory = messages.slice(-6).map(msg => ({
        role: msg.role,
        content: msg.content
      }));

      console.log("📤 Sending Request:", { question, history: cleanHistory, selected_docs: selectedDocs });

      // 3. Send Request
      const response = await queryKnowledgeBase({
        question,
        history: cleanHistory, 
        selected_docs: selectedDocs,
      });

      console.log("📥 Received Response:", response);

      // 4. ROBUST DATA EXTRACTION
      // Check if data is in response.data (Axios) or directly in response (Fetch/Custom)
      const responseData = response.data || response;
      
      if (!responseData || (!responseData.answer && !responseData.result)) {
        throw new Error("Received empty or invalid response from backend");
      }

      const answerText = responseData.answer || responseData.result || "No answer provided.";
      const contextUsed = responseData.context_used || responseData.sources || [];
      const confidenceScore = responseData.confidence || 0;

      // 5. Add AI Response
      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: answerText,
        sources: contextUsed,
        confidence: confidenceScore,
        model: responseData.model || 'unknown',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, aiMessage]);

    } catch (error) {
      console.error('❌ Chat Error:', error);
      
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `Error: ${error.message || "Failed to process response."}. Check console (F12) for details.`,
        timestamp: new Date().toISOString(),
        isError: true,
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      setActiveRequest(null);
    }
  }, [messages]);

  const clearChat = useCallback(() => {
    setMessages([]);
  }, []);

  const value = {
    messages,
    isLoading,
    activeRequest,
    sendMessage,
    clearChat,
  };

  return (
    <ChatContext.Provider value={value}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChatContext must be used within ChatProvider');
  }
  return context;
}