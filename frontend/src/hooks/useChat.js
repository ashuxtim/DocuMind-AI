import { useState, useCallback } from 'react';
import { sendChatMessage } from '@/lib/api';

export function useChat() {
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState('');

  // Send a chat message
  const sendMessage = useCallback(async (question, selectedDocs = []) => {
    if (!question.trim()) return;

    // Add user message to history
    const userMessage = {
      role: 'user',
      content: question,
      timestamp: new Date().toISOString(),
    };
    
    setChatHistory(prev => [...prev, userMessage]);
    setCurrentQuestion('');
    setIsLoading(true);

    try {
      const response = await sendChatMessage(question, chatHistory, selectedDocs);
      const { answer, context_used, confidence, model } = response.data;

      // Add AI response to history
      const aiMessage = {
        role: 'assistant',
        content: answer,
        sources: context_used || [],
        confidence: confidence || 0,
        model: model || 'unknown',
        timestamp: new Date().toISOString(),
      };

      setChatHistory(prev => [...prev, aiMessage]);
    } catch (error) {
      console.error('Chat error:', error);
      
      // Add error message
      const errorMessage = {
        role: 'assistant',
        content: `❌ **Error**: ${error.response?.data?.detail || error.message || 'Failed to get response'}`,
        timestamp: new Date().toISOString(),
      };
      
      setChatHistory(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [chatHistory]);

  // Clear chat history
  const clearChat = useCallback(() => {
    setChatHistory([]);
  }, []);

  // Add message directly (for summaries)
  const addMessage = useCallback((message) => {
    setChatHistory(prev => [...prev, { ...message, timestamp: new Date().toISOString() }]);
  }, []);

  return {
    chatHistory,
    isLoading,
    currentQuestion,
    setCurrentQuestion,
    sendMessage,
    clearChat,
    addMessage,
  };
}
