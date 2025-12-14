import { AxiosInstance } from "axios";

export const exists = async (axiosInstance: AxiosInstance, projectId: string) => {
  const response = await axiosInstance.get(`/api/model/exists/${projectId}`);
  return response.data;
};

export const train = async (axiosInstance: AxiosInstance, projectId: string, directory: string) => {
  const response = await axiosInstance.get('/api/model/train', {
    params: {
      project_id: projectId,
      directory: directory
    }
  });
  return response.data;
};

export const training_status = async (axiosInstance: AxiosInstance, training_id: string) => {
  const response = await axiosInstance.get(`/api/model/train/status/${training_id}`);
  return response.data;
};

export const generate = async (axiosInstance: AxiosInstance, prompt: string, project_id: string) => {
  const response = await axiosInstance.get('/api/model/generate', {
    params: {
      prompt: prompt,
      project_id: project_id
    }
  });
  return response.data;
};