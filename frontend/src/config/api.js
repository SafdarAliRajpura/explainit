export const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000';

export const API_ENDPOINTS = {
  GENERATE: `${API_BASE_URL}/generate`,
  UPLOAD_SOURCE: `${API_BASE_URL}/upload-source`,
  ASK_PANEL: `${API_BASE_URL}/ask-panel`,
  GENERATE_QUIZ: `${API_BASE_URL}/generate-quiz`,
  LINKEDIN_STATUS: `${API_BASE_URL}/auth/linkedin/status`,
  LINKEDIN_LOGIN: `${API_BASE_URL}/auth/linkedin/login`,
  LINKEDIN_POST_PANEL: `${API_BASE_URL}/linkedin/post-panel`,
  LINKEDIN_POST_CAROUSEL: `${API_BASE_URL}/linkedin/post-carousel`,
  GENERATE_LINKEDIN_COPY: `${API_BASE_URL}/generate-linkedin-copy`,
};
