import { AxiosInstance } from "axios";

export interface StoryPage {
  _id: string;
  project_id: string;
  user_id: string;
  page_number: number;
  page_text: string;
  text_version: number;
  illustration_prompt?: string;
  image_s3_key?: string;
  image_version: number;
  created_at: string;
  updated_at: string;
}

export const getStoryPages = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<StoryPage[]> => {
  const response = await axiosInstance.get(`/api/story-pages/project/${projectId}`);
  return response.data;
};

export const getStoryPage = async (
  axiosInstance: AxiosInstance,
  pageId: string
): Promise<StoryPage> => {
  const response = await axiosInstance.get(`/api/story-pages/${pageId}`);
  return response.data;
};

export const createStoryPage = async (
  axiosInstance: AxiosInstance,
  data: {
    project_id: string;
    page_number: number;
    page_text: string;
    illustration_prompt?: string;
  }
): Promise<StoryPage> => {
  const response = await axiosInstance.post("/api/story-pages", data);
  return response.data;
};

export const updatePageText = async (
  axiosInstance: AxiosInstance,
  pageId: string,
  pageText: string
): Promise<StoryPage> => {
  const response = await axiosInstance.put(`/api/story-pages/${pageId}/text`, {
    page_text: pageText,
  });
  return response.data;
};

export const updateIllustrationPrompt = async (
  axiosInstance: AxiosInstance,
  pageId: string,
  illustrationPrompt: string
): Promise<StoryPage> => {
  const response = await axiosInstance.put(`/api/story-pages/${pageId}/prompt`, {
    illustration_prompt: illustrationPrompt,
  });
  return response.data;
};

export const generatePageImage = async (
  axiosInstance: AxiosInstance,
  pageId: string
): Promise<StoryPage> => {
  const response = await axiosInstance.post(`/api/story-pages/${pageId}/generate-image`);
  return response.data;
};

export const deleteStoryPage = async (
  axiosInstance: AxiosInstance,
  pageId: string
): Promise<void> => {
  await axiosInstance.delete(`/api/story-pages/${pageId}`);
};

export const compileStory = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<{ message: string; pages: StoryPage[] }> => {
  const response = await axiosInstance.post(`/api/chat/story-project/${projectId}/chat/compile`);
  return response.data;
};

export const exportStoryPDF = async (
  axiosInstance: AxiosInstance,
  projectId: string
): Promise<void> => {
  const response = await axiosInstance.get(`/api/story-pages/project/${projectId}/export`, {
    responseType: 'blob'
  });

  // Create download link
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;

  // Extract filename from Content-Disposition header if available
  const contentDisposition = response.headers['content-disposition'];
  let filename = 'storybook.pdf';
  if (contentDisposition) {
    const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
    if (filenameMatch) {
      filename = filenameMatch[1];
    }
  }

  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
