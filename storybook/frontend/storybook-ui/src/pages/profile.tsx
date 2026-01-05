import { useState, useEffect } from "react";
import { Card, Input, Button, Avatar, Spinner } from "@heroui/react";
import { useAxios } from "@/hooks/axiosContext";
import { useUserContext } from "@/hooks/userContext";
import {
  getMyProfile,
  updateMyProfile,
  uploadProfileImage,
  UserProfile,
} from "@/apis/userProfileController";
import { fetchImageDownloadUrl } from "@/apis/imageController";
import DefaultLayout from "@/layouts/default";
import { useToast } from "@/hooks/useToast";

export default function ProfilePage() {
  const { axiosInstance } = useAxios();
  const { currentUser } = useUserContext();
  const { showToast, showError } = useToast();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [profileImageUrl, setProfileImageUrl] = useState<string | null>(null);

  useEffect(() => {
    fetchProfile();
  }, []);

  const fetchProfile = async () => {
    setIsLoading(true);
    try {
      const fetchedProfile = await getMyProfile(axiosInstance);
      setProfile(fetchedProfile);
      setDisplayName(fetchedProfile.display_name || "");

      // Fetch profile image if exists
      if (fetchedProfile.profile_image_id) {
        fetchProfileImage(fetchedProfile.profile_image_id);
      }
    } catch (error) {
      console.error("Error fetching profile:", error);
      showError("Failed to load profile");
    } finally {
      setIsLoading(false);
    }
  };

  const fetchProfileImage = async (imageId: string) => {
    try {
      const url = await fetchImageDownloadUrl(axiosInstance, imageId);
      setProfileImageUrl(url);
    } catch (error) {
      console.error("Error fetching profile image:", error);
    }
  };

  const handleSaveProfile = async () => {
    if (!displayName.trim()) {
      showError("Display name cannot be empty");
      return;
    }

    setIsSaving(true);
    try {
      const updatedProfile = await updateMyProfile(axiosInstance, displayName);
      setProfile(updatedProfile);
      showToast("Profile updated successfully", "success");
    } catch (error) {
      console.error("Error updating profile:", error);
      showError("Failed to update profile");
    } finally {
      setIsSaving(false);
    }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith("image/")) {
      showError("Please select an image file");
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      showError("Image size must be less than 5MB");
      return;
    }

    setIsUploadingImage(true);
    try {
      const updatedProfile = await uploadProfileImage(axiosInstance, file);
      setProfile(updatedProfile);

      // Fetch the new profile image
      if (updatedProfile.profile_image_id) {
        fetchProfileImage(updatedProfile.profile_image_id);
      }

      showToast("Profile image uploaded successfully", "success");
    } catch (error) {
      console.error("Error uploading profile image:", error);
      showError("Failed to upload profile image");
    } finally {
      setIsUploadingImage(false);
    }
  };

  if (isLoading) {
    return (
      <DefaultLayout>
        <div className="flex justify-center items-center min-h-screen">
          <Spinner size="lg" />
        </div>
      </DefaultLayout>
    );
  }

  return (
    <DefaultLayout>
      <section className="flex flex-col items-center justify-center gap-4 md:py-10">
        <div className="w-full max-w-2xl">
          <h1 className="text-3xl font-bold mb-6">Profile Settings</h1>

          <Card className="p-6">
            {/* Profile Image Section */}
            <div className="flex flex-col items-center gap-4 mb-8">
              <Avatar
                src={profileImageUrl || undefined}
                className="w-32 h-32"
                name={displayName || currentUser?.username}
                isBordered
                color="primary"
              />

              <div className="flex flex-col items-center gap-2">
                <label
                  htmlFor="profile-image-upload"
                  className="cursor-pointer"
                >
                  <Button
                    as="span"
                    color="primary"
                    variant="flat"
                    isLoading={isUploadingImage}
                  >
                    {profileImageUrl ? "Change Photo" : "Upload Photo"}
                  </Button>
                </label>
                <input
                  id="profile-image-upload"
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleImageUpload}
                  disabled={isUploadingImage}
                />
                <p className="text-xs text-gray-500">
                  Maximum file size: 5MB
                </p>
              </div>
            </div>

            {/* Profile Info Section */}
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">
                  Email
                </label>
                <p className="text-sm text-gray-600 dark:text-gray-400 py-2">
                  {currentUser?.email || "Not set"}
                </p>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">
                  Display Name *
                </label>
                <Input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Enter your display name"
                  description="This name will be shown when you create content"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  color="primary"
                  onPress={handleSaveProfile}
                  isLoading={isSaving}
                  isDisabled={!displayName.trim() || displayName === profile?.display_name}
                >
                  Save Changes
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </section>
    </DefaultLayout>
  );
}
