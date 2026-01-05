import { AxiosInstance } from "axios";

export const ready = async (axiosInstance: AxiosInstance, projectId: string) => {
  const response = await axiosInstance.get(`/api/model/ready/${projectId}`);
  return response.data;
};

export const train = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  imageIds?: string[],
) => {
  const payload: { project_id: string; image_ids?: string[] } = {
    project_id: projectId,
  };
  if (imageIds && imageIds.length) {
    payload.image_ids = imageIds;
  }

  const response = await axiosInstance.post('/api/model/train', payload);
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

export const deleteTrainingRun = async (axiosInstance: AxiosInstance, trainingRunId: string) => {
  const response = await axiosInstance.delete(`/api/model/training-runs/${trainingRunId}`);
  return response.data;
};

type GenerateOptions = {
  referenceImageIds?: string[];
  includeSubjectDescription?: boolean;
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
    include_subject_description: options.includeSubjectDescription,
  });
  return response.data;
};
