import { AxiosInstance } from 'axios';

export type CharacterAsset = {
  _id: string;
  project_id: string;
  user_id: string;
  asset_type: 'portrait' | 'preview_scene' | 'character_bible';
  image_id?: string;
  prompt?: string;
  scene_name?: string;
  bible_data?: any;
  stability_image_id?: string;
  is_approved: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

// Get all character assets for a project
export const getCharacterAssets = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  assetType?: string
): Promise<CharacterAsset[]> => {
  const params = assetType ? { type: assetType } : {};
  const response = await axiosInstance.get(`/api/characters/project/${projectId}`, { params });
  return response.data;
};

// Generate character portrait
export const generateCharacterPortrait = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  userDescription?: string,
  style?: string
): Promise<CharacterAsset> => {
  const response = await axiosInstance.post(
    `/api/characters/project/${projectId}/portrait`,
    {
      user_description: userDescription,
      style: style
    }
  );
  return response.data;
};

// Generate preview scenes
export const generatePreviewScenes = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  scenes: string[] = ['park', 'space', 'pirate'],
  style?: string
): Promise<{ scenes: CharacterAsset[] }> => {
  const response = await axiosInstance.post(
    `/api/characters/project/${projectId}/preview-scenes`,
    { scenes, style }
  );
  return response.data;
};

// Approve character asset
export const approveCharacterAsset = async (
  axiosInstance: AxiosInstance,
  assetId: string
): Promise<CharacterAsset> => {
  const response = await axiosInstance.post(`/api/characters/asset/${assetId}/approve`);
  return response.data;
};

// Regenerate character asset
export const regenerateCharacterAsset = async (
  axiosInstance: AxiosInstance,
  assetId: string,
  userDescription?: string,
  style?: string
): Promise<CharacterAsset> => {
  const response = await axiosInstance.post(
    `/api/characters/asset/${assetId}/regenerate`,
    {
      user_description: userDescription,
      style: style
    }
  );
  return response.data;
};

// Create or update character bible
export const createCharacterBible = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  bibleData: any
): Promise<CharacterAsset> => {
  const response = await axiosInstance.post(
    `/api/characters/project/${projectId}/bible`,
    { bible_data: bibleData }
  );
  return response.data;
};

// Get character bible
export const getCharacterBible = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<CharacterAsset | null> => {
  try {
    const response = await axiosInstance.get(`/api/characters/project/${projectId}/bible`);
    return response.data;
  } catch (error: any) {
    if (error.response?.status === 404) {
      return null;
    }
    throw error;
  }
};
