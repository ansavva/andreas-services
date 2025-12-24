import { AxiosInstance } from 'axios';

export type ChildProfile = {
  _id: string;
  project_id: string;
  user_id: string;
  child_name: string;
  child_age: number;
  consent_given: boolean;
  consent_timestamp?: string;
  photo_ids: string[];
  created_at: string;
  updated_at: string;
};

// Get child profile by project ID
export const getChildProfileByProject = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<ChildProfile | null> => {
  try {
    const response = await axiosInstance.get(`/api/child-profiles/project/${projectId}`);
    return response.data;
  } catch (error: any) {
    if (error.response?.status === 404) {
      return null;
    }
    throw error;
  }
};

// Get child profile by ID
export const getChildProfileById = async (
  axiosInstance: AxiosInstance,
  profileId: string
): Promise<ChildProfile> => {
  const response = await axiosInstance.get(`/api/child-profiles/${profileId}`);
  return response.data;
};

// Create child profile
export const createChildProfile = async (
  axiosInstance: AxiosInstance,
  data: {
    project_id: string;
    child_name: string;
    child_age: number;
    consent_given: boolean;
    photo_ids?: string[];
  }
): Promise<ChildProfile> => {
  const response = await axiosInstance.post('/api/child-profiles', data);
  return response.data;
};

// Update child profile
export const updateChildProfile = async (
  axiosInstance: AxiosInstance,
  profileId: string,
  updates: {
    child_name?: string;
    child_age?: number;
    photo_ids?: string[];
  }
): Promise<ChildProfile> => {
  const response = await axiosInstance.put(`/api/child-profiles/${profileId}`, updates);
  return response.data;
};

// Delete child profile
export const deleteChildProfile = async (
  axiosInstance: AxiosInstance,
  profileId: string
): Promise<void> => {
  await axiosInstance.delete(`/api/child-profiles/${profileId}`);
};
