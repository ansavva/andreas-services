import { AxiosInstance } from "axios";

export const uploadImage = async (
    axiosInstance: AxiosInstance,
    projectId: string,
    directory: string,
    files: File[]
  ) => {
    const formData = new FormData();
    formData.append("project_id", projectId);
    formData.append("directory", directory);
  
    // Append all files to FormData
    files.forEach((file, index) => {
        formData.append(`image[${index}]`, file); // Index added here
      });    
  
    try {
      const response = await axiosInstance.post("/images/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      return response.data.upload_results; // Return upload results
    } catch (error) {
      console.error("Upload failed:", error);
      return [];
    }
  };
  

export const downloadImage = async (axiosInstance: AxiosInstance, projectId: string, directory: string, key: string) => {
    const response = await axiosInstance.get(`/images/download`, {
        params: { project_id: projectId, directory, key },
        responseType: "blob",
    });
    return response.data;
};

export const deleteImage = async (axiosInstance: AxiosInstance, projectId: string, directory: string, key: string) => {
    const response = await axiosInstance.delete(`/images/delete`, {
        params: { project_id: projectId, directory, key },
    });
    return response.data;
};

export const listImages = async (axiosInstance: AxiosInstance, projectId: string, directory: string) => {
    const response = await axiosInstance.get(`/images/list`, {
        params: { project_id: projectId, directory },
    });
    return response.data;
};
