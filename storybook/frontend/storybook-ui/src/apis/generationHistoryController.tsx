import { AxiosInstance } from "axios";

export interface GenerationHistoryItem {
  id: string;
  project_id: string;
  user_id: string;  // Cognito user ID (sub) of the creator
  prompt: string;
  image_ids: string[];
  reference_image_ids?: string[];
  image_processing?: Record<string, boolean>;
  include_subject_description?: boolean;
  status?: string;
  prediction_id?: string | null;
  provider?: string | null;
  error_message?: string | null;
  created_at: string;
  user_profile?: {
    display_name: string | null;
    profile_image_id: string | null;
  };
}

export const getGenerationHistory = async (
  axiosInstance: AxiosInstance,
  historyId: string
): Promise<GenerationHistoryItem> => {
  const response = await axiosInstance.get(
    `/api/generation-history/${historyId}`
  );
  return response.data;
};

export const updateGenerationHistoryStatus = async (
  axiosInstance: AxiosInstance,
  historyId: string
): Promise<GenerationHistoryItem> => {
  const response = await axiosInstance.get(
    `/api/generation-history/${historyId}/status`
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

export const getDraftGenerationHistory = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<GenerationHistoryItem | null> => {
  const response = await axiosInstance.get(
    `/api/generation-history/draft/${projectId}`
  );
  return response.data.history || null;
};

export const updateDraftGenerationPrompt = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  prompt: string,
  includeSubjectDescription?: boolean
): Promise<GenerationHistoryItem> => {
  const response = await axiosInstance.put(
    `/api/generation-history/draft/${projectId}/prompt`,
    { prompt, include_subject_description: includeSubjectDescription }
  );
  return response.data;
};

export const deleteGenerationHistory = async (
  axiosInstance: AxiosInstance,
  historyId: string
): Promise<void> => {
  await axiosInstance.delete(`/api/generation-history/${historyId}`);
};
