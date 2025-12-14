import { AxiosInstance } from 'axios';

// Function to get all projects
export const getProjects = async (axiosInstance: AxiosInstance) => {
  const response = await axiosInstance.get('/api/projects');
  return response.data;  // returns an array of projects
};

// Function to get a specific project by ID
export const getProjectById = async (axiosInstance: AxiosInstance, projectId: string) => {
  const response = await axiosInstance.get(`/api/projects/${projectId}`);
  return response.data;  // returns the project object
};

// Function to create a new project
export const createProject = async (axiosInstance: AxiosInstance, name: string, subjectName: string) => {
  const response = await axiosInstance.post('/api/projects', { name, subjectName });
  return response.data;  // returns the newly created project
};