import { AxiosInstance } from "axios";

export interface GenerationHistoryItem {
  id: string;
  project_id: string;
  user_id: string;  // Cognito user ID (sub) of the creator
  prompt: string;
  image_ids: string[];
  reference_image_ids?: string[];
  created_at: string;
  user_profile?: {
    display_name: string | null;
    profile_image_id: string | null;
  };
}

export const createGenerationHistory = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  prompt: string,
  imageIds: string[],
  referenceImageIds?: string[]
): Promise<GenerationHistoryItem> => {
  const response = await axiosInstance.post("/api/generation-history/create", {
    project_id: projectId,
    prompt: prompt,
    image_ids: imageIds,
    reference_image_ids: referenceImageIds,
  });
  return response.data;
};

export const getGenerationHistory = async (
  axiosInstance: AxiosInstance,
  historyId: string
): Promise<GenerationHistoryItem> => {
  const response = await axiosInstance.get(
    `/api/generation-history/${historyId}`
  );
  return response.data;
};

export const listGenerationHistory = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<GenerationHistoryItem[]> => {
  const response = await axiosInstance.get(
    `/api/generation-history/project/${projectId}`
  );
  return response.data.histories || [];
};

export const deleteGenerationHistory = async (
  axiosInstance: AxiosInstance,
  historyId: string
): Promise<void> => {
  await axiosInstance.delete(`/api/generation-history/${historyId}`);
};
