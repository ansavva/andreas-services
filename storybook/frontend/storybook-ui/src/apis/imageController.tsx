import { AxiosInstance } from "axios";

type UploadImageOptions = {
  resize?: boolean;
};

type PresignedUpload = {
  image_id: string;
  filename: string;
  content_type: string;
  resize?: boolean;
  upload_url: string;
  method?: string;
  headers?: Record<string, string>;
};

export const uploadImage = async (
  axiosInstance: AxiosInstance,
  projectId: string,
  _directory: string,
  files: File[],
  imageType: string = "training",
  options?: UploadImageOptions,
) => {
  if (!files.length) {
    return { images: [] };
  }

  const shouldResize = options?.resize ?? true;

  const filePayload = files.map((file) => ({
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    resize: shouldResize,
  }));

  const presignResponse = await axiosInstance.post("/api/images/upload/presign", {
    project_id: projectId,
    image_type: imageType,
    files: filePayload,
  });

  const presignedUploads: PresignedUpload[] = presignResponse.data.uploads || [];

  if (presignedUploads.length !== files.length) {
    throw new Error("Presigned upload mismatch");
  }

  await Promise.all(
    presignedUploads.map(async (upload, index) => {
      const file = files[index];
      const url = upload.upload_url;
      if (!url) {
        throw new Error("Missing upload URL in presigned response");
      }
      const method = upload.method || "PUT";
      if (method !== "PUT") {
        throw new Error(`Unsupported upload method: ${method}`);
      }
      const headers: Record<string, string> = {
        "Content-Type": file.type || "application/octet-stream",
        ...(upload.headers || {}),
      };

      const response = await fetch(url, {
        method,
        headers,
        body: file,
      });

      if (!response.ok) {
        throw new Error(`Failed to upload ${file.name} to S3`);
      }
    }),
  );

  const completeResponse = await axiosInstance.post("/api/images/upload/dispatch", {
    project_id: projectId,
    image_type: imageType,
    uploads: presignedUploads.map((upload, index) => ({
      image_id: upload.image_id,
      filename: files[index].name,
      content_type: files[index].type || "application/octet-stream",
      resize: upload.resize ?? shouldResize,
    })),
  });

  return completeResponse.data;
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

export const listImages = async (axiosInstance: AxiosInstance, projectId: string, _directory?: string, imageType?: string) => {
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

export const getAvailableTrainingImages = async (axiosInstance: AxiosInstance, projectId: string) => {
    const response = await axiosInstance.get(`/api/images/available/${projectId}`);
    return response.data;
};

export const getDraftTrainingImages = async (axiosInstance: AxiosInstance, projectId: string) => {
    const response = await axiosInstance.get(`/api/images/draft/${projectId}`);
    return response.data;
};

export const getImageStatus = async (axiosInstance: AxiosInstance, imageIds: string[]) => {
    if (!imageIds.length) {
        return { images: [] };
    }

    const response = await axiosInstance.get(`/api/images/status`, {
        params: { ids: imageIds.join(",") },
    });
    return response.data;
};
