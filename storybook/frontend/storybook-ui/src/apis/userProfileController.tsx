import { AxiosInstance } from "axios";

export interface UserProfile {
  user_id: string;
  display_name: string | null;
  profile_image_id: string | null;
  created_at?: string;
  updated_at?: string;
}

export const getMyProfile = async (
  axiosInstance: AxiosInstance
): Promise<UserProfile> => {
  const response = await axiosInstance.get("/api/user-profile/me");
  return response.data;
};

export const updateMyProfile = async (
  axiosInstance: AxiosInstance,
  displayName: string
): Promise<UserProfile> => {
  const response = await axiosInstance.put("/api/user-profile/me", {
    display_name: displayName,
  });
  return response.data;
};

export const uploadProfileImage = async (
  axiosInstance: AxiosInstance,
  imageFile: File
): Promise<UserProfile> => {
  const formData = new FormData();
  formData.append("image", imageFile);

  const response = await axiosInstance.post(
    "/api/user-profile/me/profile-image",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return response.data;
};

export const getUserProfile = async (
  axiosInstance: AxiosInstance,
  userId: string
): Promise<UserProfile> => {
  const response = await axiosInstance.get(`/api/user-profile/${userId}`);
  return response.data;
};
