import { AxiosInstance } from 'axios';

export type StoryProject = {
  _id: string;
  name: string;
  user_id: string;
  status: string;
  child_profile_id?: string;
  character_bible_id?: string;
  story_state_id?: string;
  created_at: string;
  updated_at: string;
};

// Get all story projects
export const getStoryProjects = async (axiosInstance: AxiosInstance): Promise<StoryProject[]> => {
  const response = await axiosInstance.get('/api/story-projects');
  return response.data;
};

// Get a specific story project by ID
export const getStoryProjectById = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<StoryProject> => {
  const response = await axiosInstance.get(`/api/story-projects/${projectId}`);
  return response.data;
};

// Create a new story project
export const createStoryProject = async (
  axiosInstance: AxiosInstance,
  name: string
): Promise<StoryProject> => {
  const response = await axiosInstance.post('/api/story-projects', { name });
  return response.data;
};

// Update story project status
export const updateStoryProjectStatus = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  status: string
): Promise<StoryProject> => {
  const response = await axiosInstance.put(`/api/story-projects/${projectId}/status`, { status });
  return response.data;
};

// Update story project fields
export const updateStoryProject = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  updates: {
    name?: string;
    child_profile_id?: string;
    character_bible_id?: string;
    story_state_id?: string;
  }
): Promise<StoryProject> => {
  const response = await axiosInstance.put(`/api/story-projects/${projectId}`, updates);
  return response.data;
};

// Delete a story project
export const deleteStoryProject = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<void> => {
  await axiosInstance.delete(`/api/story-projects/${projectId}`);
};
