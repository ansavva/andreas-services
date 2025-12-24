import { AxiosInstance } from "axios";

type UploadImageOptions = {
  normalize?: boolean;
};

export const uploadImage = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  directory: string,
  files: File[],
  imageType: string = "training",
  options?: UploadImageOptions,
) => {
    const formData = new FormData();
    formData.append("project_id", projectId);
    formData.append("directory", directory);
    formData.append("image_type", imageType);
    const shouldNormalize = options?.normalize ?? true;
    formData.append("normalize_images", shouldNormalize ? "true" : "false");

    // Append all files to FormData
    files.forEach((file, index) => {
        formData.append(`image[${index}]`, file); // Index added here
      });

    try {
      const response = await axiosInstance.post("/api/images/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      return response.data; // Return the full response data which contains "images" array
    } catch (error) {
      console.error("Upload failed:", error);
      throw error; // Throw error instead of returning empty array so caller can handle it
    }
  };


export const downloadImage = async (axiosInstance: AxiosInstance, projectId: string, directory: string, key: string) => {
    const response = await axiosInstance.get(`/api/images/download`, {
        params: { project_id: projectId, directory, key },
        responseType: "blob",
    });
    return response.data;
};

export const downloadImageById = async (axiosInstance: AxiosInstance, imageId: string) => {
    const response = await axiosInstance.get(`/api/images/download/${imageId}`, {
        responseType: "blob",
    });
    return response.data;
};

export const deleteImage = async (axiosInstance: AxiosInstance, imageId: string) => {
    const response = await axiosInstance.delete(`/api/images/delete/${imageId}`);
    return response.data;
};

export const listImages = async (axiosInstance: AxiosInstance, projectId: string, directory?: string, imageType?: string) => {
    // Note: directory parameter is kept for backwards compatibility but not used
    const params = imageType ? { image_type: imageType } : {};
    const response = await axiosInstance.get(`/api/images/list/${projectId}`, { params });
    return response.data;
};

export const getImagesByProject = async (axiosInstance: AxiosInstance, projectId: string, imageType?: string) => {
    const params = imageType ? { image_type: imageType } : {};
    const response = await axiosInstance.get(`/api/images/list/${projectId}`, { params });
    return response.data;
};
