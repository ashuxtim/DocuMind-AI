import axios from 'axios';

const API_BASE_URL = '/api';

// Create axios instance with base configuration
export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// API endpoints
export const endpoints = {
  upload: '/upload',
  documents: '/documents',
  delete: (filename) => `/delete/${filename}`,
  status: (taskId) => `/status/${taskId}`,
  cancel: (taskId) => `/cancel/${taskId}`,
  query: '/query',
  summarize: (filename) => `/summarize/${filename}`,
  graph: '/graph',
  dashboard: '/dashboard',
};

// Document Management APIs
export const uploadDocument = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post(endpoints.upload, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const getDocuments = () => api.get(endpoints.documents);

export const deleteDocument = (filename) => api.delete(endpoints.delete(filename));

export const getTaskStatus = (taskId) => api.get(endpoints.status(taskId));

export const cancelTask = (taskId) => api.post(endpoints.cancel(taskId));

// Chat/Query APIs
export const queryKnowledgeBase = (data) => {
  return api.post(endpoints.query, data);
};

// Summary APIs
export const summarizeDocument = (filename) => {
  return api.post(endpoints.summarize(filename));
};

// Graph APIs
export const getGraph = (limit) =>
  api.get(endpoints.graph, { params: limit ? { limit } : undefined });

// Dashboard APIs
export const getDashboard = () => api.get(endpoints.dashboard);

export default api;