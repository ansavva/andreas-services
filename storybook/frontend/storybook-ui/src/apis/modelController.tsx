import { AxiosInstance } from "axios";

export const exists = async (axiosInstance: AxiosInstance, projectId: string) => {
  const response = await axiosInstance.get(`/api/model/exists/${projectId}`);
  return response.data;
};

export const train = async (axiosInstance: AxiosInstance, projectId: string, imageIds: string[]) => {
  const response = await axiosInstance.post('/api/model/train', {
    project_id: projectId,
    image_ids: imageIds
  });
  return response.data;
};

export const training_status = async (axiosInstance: AxiosInstance, training_id: string) => {
  const response = await axiosInstance.get(`/api/model/train/status/${training_id}`);
  return response.data;
};

export const getTrainingRuns = async (axiosInstance: AxiosInstance, projectId: string) => {
  const response = await axiosInstance.get(`/api/model/training-runs/${projectId}`);
  return response.data;
};

export const updateTrainingRunStatus = async (axiosInstance: AxiosInstance, trainingRunId: string) => {
  const response = await axiosInstance.get(`/api/model/training-runs/${trainingRunId}/status`);
  return response.data;
};

type GenerateOptions = {
  referenceImageIds?: string[];
};

export const generate = async (
  axiosInstance: AxiosInstance,
  prompt: string,
  project_id: string,
  options: GenerateOptions = {},
) => {
  const response = await axiosInstance.post("/api/model/generate", {
    prompt,
    project_id,
    reference_image_ids: options.referenceImageIds,
  });
  return response.data;
};
