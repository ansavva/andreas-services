import { AxiosInstance } from 'axios';

// Function to get all model projects
export const getModelProjects = async (axiosInstance: AxiosInstance) => {
  const response = await axiosInstance.get('/api/model-projects');
  return response.data;  // returns an array of model projects
};

// Function to get a specific model project by ID
export const getModelProjectById = async (axiosInstance: AxiosInstance, projectId: string) => {
  const response = await axiosInstance.get(`/api/model-projects/${projectId}`);
  return response.data;  // returns the model project object
};

// Function to create a new model project
export const createModelProject = async (axiosInstance: AxiosInstance, name: string, subjectName: string, modelType: string) => {
  const response = await axiosInstance.post('/api/model-projects', { name, subjectName, modelType });
  return response.data;  // returns the newly created model project
};

// Fetch available model types from backend config
export const getModelTypes = async (axiosInstance: AxiosInstance) => {
  const response = await axiosInstance.get('/api/model-projects/model-types');
  return response.data;
};

// Function to update model project status
export const updateModelProjectStatus = async (axiosInstance: AxiosInstance, projectId: string, status: string) => {
  const response = await axiosInstance.put(`/api/model-projects/${projectId}/status`, { status });
  return response.data;  // returns the updated model project
};

// Function to update model project fields
export const updateModelProject = async (axiosInstance: AxiosInstance, projectId: string, updates: { name?: string; subjectName?: string; modelType?: string }) => {
  const response = await axiosInstance.put(`/api/model-projects/${projectId}`, updates);
  return response.data;  // returns the updated model project
};

// Function to delete a model project
export const deleteModelProject = async (axiosInstance: AxiosInstance, projectId: string) => {
  const response = await axiosInstance.delete(`/api/model-projects/${projectId}`);
  return response.data;  // returns success message
};
