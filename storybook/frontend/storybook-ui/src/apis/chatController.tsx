import { AxiosInstance } from 'axios';

export type ChatMessage = {
  _id: string;
  project_id: string;
  user_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  sequence: number;
  model?: string;
  tokens_used?: number;
  structured_data?: any;
  created_at: string;
};

export type StoryState = {
  _id: string;
  project_id: string;
  user_id: string;
  version: number;
  title?: string;
  age_range?: string;
  characters?: any[];
  setting?: string;
  outline?: string[];
  page_count?: number;
  themes?: string[];
  tone?: string;
  is_current: boolean;
  created_at: string;
  updated_at: string;
};

// Get chat messages for a project
export const getChatMessages = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  limit?: number
): Promise<ChatMessage[]> => {
  const params = limit ? { limit } : {};
  const response = await axiosInstance.get(`/api/chat/story-project/${projectId}/chat/messages`, { params });
  return response.data.messages;
};

// Send a chat message
export const sendChatMessage = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  message: string
): Promise<{ message: string; model: string; tokens_used: number }> => {
  const response = await axiosInstance.post(`/api/chat/story-project/${projectId}/chat/messages`, {
    message,
  });
  return response.data;
};

// Generate story state from conversation
export const generateStoryState = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<{ story_state: StoryState; tokens_used: number }> => {
  const response = await axiosInstance.post(`/api/chat/story-project/${projectId}/chat/state/generate`);
  return response.data;
};

// Get current story state
export const getStoryState = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<StoryState | null> => {
  try {
    const response = await axiosInstance.get(`/api/chat/story-project/${projectId}/chat/state`);
    return response.data;
  } catch (error: any) {
    if (error.response?.status === 404) {
      return null;
    }
    throw error;
  }
};

// Get all story state versions
export const getStoryStateVersions = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<StoryState[]> => {
  const response = await axiosInstance.get(`/api/chat/story-project/${projectId}/chat/state/versions`);
  return response.data.versions;
};

// Clear chat conversation
export const clearChat = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<void> => {
  await axiosInstance.delete(`/api/chat/story-project/${projectId}/chat/messages`);
};

export const getModelProjectChatMessages = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  limit?: number
): Promise<ChatMessage[]> => {
  const params = limit ? { limit } : {};
  const response = await axiosInstance.get(`/api/chat/model-project/${projectId}/chat/messages`, { params });
  return response.data.messages;
};

export const sendModelProjectChatMessage = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  message: string
): Promise<{ message: string; model: string; tokens_used: number }> => {
  const response = await axiosInstance.post(`/api/chat/model-project/${projectId}/chat/messages`, {
    message,
  });
  return response.data;
};

export const clearModelProjectChat = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<void> => {
  await axiosInstance.delete(`/api/chat/model-project/${projectId}/chat/messages`);
};
