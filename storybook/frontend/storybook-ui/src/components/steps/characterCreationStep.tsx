import React, { useState, useRef, useEffect } from "react";
import {
  Button,
  Card,
  CardBody,
  Input,
  Select,
  SelectItem,
  Spinner,
  Textarea,
} from "@nextui-org/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faUpload,
  faWandMagicSparkles,
  faCheck,
  faRefresh,
  faTrash,
} from "@fortawesome/free-solid-svg-icons";
import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";
import { uploadImage, deleteImage, downloadImageById } from "@/apis/imageController";
import { getStylePresets } from "@/apis/configController";
import { generateCharacterPortrait, approveCharacterAsset, regenerateCharacterAsset, getCharacterAssets } from "@/apis/characterController";
import ImageGrid from "@/components/images/imageGrid";

type PhotoFile = {
  id: string;
  name?: string;
};

type CharacterAsset = {
  _id: string;
  project_id: string;
  asset_type: string;
  image_id: string;
  is_approved: boolean;
  version: number;
};

type CharacterCreationStepProps = {
  projectId: string;
  onContinue: () => void;
  onBack: () => void;
};

const CharacterCreationStep: React.FC<CharacterCreationStepProps> = ({
  projectId,
  onContinue,
  onBack,
}) => {
  const { axiosInstance } = useAxios();
  const { showError, showSuccess } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Photos state
  const [photos, setPhotos] = useState<PhotoFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  // Prompt state
  const [userDescription, setUserDescription] = useState<string>("");
  const [selectedStyle, setSelectedStyle] = useState<string>("");
  const [stylePresets, setStylePresets] = useState<string[]>([]);
  const [defaultStyle, setDefaultStyle] = useState<string>("");

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedPortrait, setGeneratedPortrait] = useState<CharacterAsset | null>(null);
  const [portraitImageData, setPortraitImageData] = useState<string | null>(null);

  // Load style presets on mount
  useEffect(() => {
    const loadStylePresets = async () => {
      try {
        const response = await getStylePresets(axiosInstance);
        setStylePresets(response.presets);
        setDefaultStyle(response.default);
        setSelectedStyle(response.default);
      } catch (error) {
        console.error("Failed to load style presets:", error);
      }
    };

    loadStylePresets();
  }, [axiosInstance]);

  // Load existing portrait and photos if any
  useEffect(() => {
    const loadExistingData = async () => {
      try {
        // Load portrait
        const assets = await getCharacterAssets(axiosInstance, projectId, "portrait");
        if (assets.length > 0) {
          setGeneratedPortrait(assets[0]);
          // Fetch portrait image data
          const imageBlob = await downloadImageById(axiosInstance, assets[0].image_id);
          const reader = new FileReader();
          reader.onloadend = () => {
            setPortraitImageData(reader.result as string);
          };
          reader.readAsDataURL(imageBlob);
        }

        // Load photos from child profile
        const profileResponse = await axiosInstance.get(`/api/child-profiles/project/${projectId}`);
        if (profileResponse.data && profileResponse.data.photo_ids) {
          const photoFiles: PhotoFile[] = profileResponse.data.photo_ids.map((id: string) => ({
            id: id,
            name: `Photo ${id.substring(0, 8)}`
          }));
          setPhotos(photoFiles);
        }
      } catch (error) {
        console.error("Failed to load existing data:", error);
      }
    };

    loadExistingData();
  }, [axiosInstance, projectId]);

  const allowedFileTypes = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
  const maxFileSize = 10 * 1024 * 1024; // 10MB
  const maxPhotos = 5;

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    const filesToUpload: File[] = [];
    let errorMsg = "";

    if (photos.length + files.length > maxPhotos) {
      showError(`You can only upload up to ${maxPhotos} photos`);
      return;
    }

    for (let i = 0; i < files.length; i++) {
      const file = files[i];

      if (!allowedFileTypes.includes(file.type)) {
        errorMsg = `File ${file.name} is not a valid image type`;
        continue;
      }

      if (file.size > maxFileSize) {
        errorMsg = `File ${file.name} is too large (max 10MB)`;
        continue;
      }

      filesToUpload.push(file);
    }

    if (errorMsg) {
      showError(errorMsg);
    }

    if (filesToUpload.length === 0) {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    setIsUploading(true);
    try {
      const result = await uploadImage(axiosInstance, projectId, 'child_photos', filesToUpload);
      const newPhotos: PhotoFile[] = result.images.map((img: any, idx: number) => ({
        id: img.id,
        name: filesToUpload[idx].name
      }));

      // Update child profile with new photo IDs
      const updatedPhotoIds = [...photos.map(p => p.id), ...newPhotos.map(p => p.id)];
      await axiosInstance.put(`/api/child-profiles/project/${projectId}`, {
        photo_ids: updatedPhotoIds
      });

      setPhotos((prev) => [...prev, ...newPhotos]);
      showSuccess(`Successfully uploaded ${newPhotos.length} photo${newPhotos.length > 1 ? 's' : ''}`);
    } catch (error) {
      showError("Failed to upload photos. Please try again.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDeletePhoto = async (photoId: string) => {
    try {
      await deleteImage(axiosInstance, photoId);

      // Update child profile to remove the photo ID
      const updatedPhotos = photos.filter((p) => p.id !== photoId);
      const updatedPhotoIds = updatedPhotos.map(p => p.id);
      await axiosInstance.put(`/api/child-profiles/project/${projectId}`, {
        photo_ids: updatedPhotoIds
      });

      setPhotos(updatedPhotos);
      showSuccess("Photo deleted");
    } catch (error) {
      showError("Failed to delete photo");
    }
  };

  const handleGenerate = async () => {
    if (photos.length === 0) {
      showError("Please upload at least one photo");
      return;
    }

    setIsGenerating(true);
    try {
      const result = await generateCharacterPortrait(
        axiosInstance,
        projectId,
        userDescription || undefined,
        selectedStyle || undefined
      );
      setGeneratedPortrait(result);

      // Fetch the image data for display
      const imageBlob = await downloadImageById(axiosInstance, result.image_id);
      const reader = new FileReader();
      reader.onloadend = () => {
        setPortraitImageData(reader.result as string);
      };
      reader.readAsDataURL(imageBlob);

      showSuccess("Character portrait generated successfully!");
    } catch (error: any) {
      console.error("Failed to generate portrait:", error);
      showError(error.response?.data?.error || "Failed to generate portrait. Please try again.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleRegenerate = async () => {
    if (!generatedPortrait) return;

    setIsGenerating(true);
    try {
      const result = await regenerateCharacterAsset(
        axiosInstance,
        generatedPortrait._id,
        userDescription || undefined,
        selectedStyle || undefined
      );
      setGeneratedPortrait(result);

      // Fetch the new image data for display
      const imageBlob = await downloadImageById(axiosInstance, result.image_id);
      const reader = new FileReader();
      reader.onloadend = () => {
        setPortraitImageData(reader.result as string);
      };
      reader.readAsDataURL(imageBlob);

      showSuccess("Character portrait regenerated!");
    } catch (error: any) {
      console.error("Failed to regenerate portrait:", error);
      showError(error.response?.data?.error || "Failed to regenerate portrait. Please try again.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleApprove = async () => {
    if (!generatedPortrait) return;

    try {
      const result = await approveCharacterAsset(axiosInstance, generatedPortrait._id);
      setGeneratedPortrait(result);
      showSuccess("Character portrait approved! You can now continue.");
    } catch (error) {
      showError("Failed to approve portrait. Please try again.");
    }
  };

  const canContinue = generatedPortrait?.is_approved;

  return (
    <div className="max-w-7xl mx-auto">
      <h3 className="text-2xl font-bold mb-2">Create Your Character</h3>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Upload photos, customize the description and style, then generate your character portrait.
        You can regenerate as many times as you'd like before approving!
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Panel: Controls */}
        <div className="space-y-4">
          {/* Photo Upload */}
          <Card>
            <CardBody className="p-6">
              <h4 className="text-lg font-semibold mb-3">Upload Photos</h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                Upload 1-{maxPhotos} photos of your child (JPG, PNG, HEIC)
              </p>

              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                accept={allowedFileTypes.join(",")}
                multiple
                className="hidden"
              />

              <Button
                color="primary"
                variant="flat"
                startContent={<FontAwesomeIcon icon={faUpload} />}
                onPress={handleFileSelect}
                isDisabled={isUploading || photos.length >= maxPhotos}
                isLoading={isUploading}
                className="mb-4"
              >
                {isUploading ? "Uploading..." : "Select Photos"}
              </Button>

              {photos.length > 0 && (
                <ImageGrid
                  images={photos}
                  onImageDelete={handleDeletePhoto}
                />
              )}
            </CardBody>
          </Card>

          {/* Description and Style */}
          <Card>
            <CardBody className="p-6 space-y-4">
              <div>
                <Textarea
                  label="Custom Description (Optional)"
                  placeholder="E.g., wearing glasses, has curly hair, big smile..."
                  value={userDescription}
                  onValueChange={setUserDescription}
                  maxRows={3}
                  description="Add details to customize the generated character"
                />
              </div>

              <div>
                <Select
                  label="Art Style"
                  placeholder="Select a style"
                  selectedKeys={selectedStyle ? [selectedStyle] : []}
                  onChange={(e) => setSelectedStyle(e.target.value)}
                >
                  {stylePresets.map((preset) => (
                    <SelectItem key={preset} value={preset}>
                      {preset.split('-').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                    </SelectItem>
                  ))}
                </Select>
              </div>
            </CardBody>
          </Card>

          {/* Generate Button */}
          <Button
            color="primary"
            size="lg"
            className="w-full"
            startContent={<FontAwesomeIcon icon={faWandMagicSparkles} />}
            onPress={generatedPortrait ? handleRegenerate : handleGenerate}
            isLoading={isGenerating}
            isDisabled={photos.length === 0 || isGenerating}
          >
            {isGenerating
              ? "Generating..."
              : generatedPortrait
              ? "Regenerate Portrait"
              : "Generate Portrait"}
          </Button>
        </div>

        {/* Right Panel: Generated Portrait */}
        <Card>
          <CardBody className="p-6 min-h-[600px] flex flex-col items-center justify-center">
            {!generatedPortrait && !isGenerating && (
              <div className="text-center text-gray-500 dark:text-gray-400">
                <FontAwesomeIcon icon={faWandMagicSparkles} size="3x" className="mb-4 opacity-30" />
                <p>Your generated character will appear here</p>
              </div>
            )}

            {isGenerating && (
              <div className="text-center">
                <Spinner size="lg" />
                <p className="mt-4 text-gray-600 dark:text-gray-400">
                  Creating your character portrait...
                </p>
              </div>
            )}

            {generatedPortrait && !isGenerating && portraitImageData && (
              <div className="w-full">
                <div className="relative aspect-square max-w-md mx-auto mb-4">
                  <img
                    src={portraitImageData}
                    alt="Generated Character"
                    className="w-full h-full object-cover rounded-lg cursor-pointer"
                    onClick={() => {
                      // TODO: Open in modal if needed
                    }}
                  />
                </div>

                <div className="flex gap-3 justify-center">
                  <Button
                    color={generatedPortrait.is_approved ? "success" : "default"}
                    variant={generatedPortrait.is_approved ? "solid" : "flat"}
                    startContent={<FontAwesomeIcon icon={faCheck} />}
                    onPress={handleApprove}
                    isDisabled={generatedPortrait.is_approved}
                  >
                    {generatedPortrait.is_approved ? "Approved" : "Approve"}
                  </Button>

                  <Button
                    variant="flat"
                    startContent={<FontAwesomeIcon icon={faRefresh} />}
                    onPress={handleRegenerate}
                    isDisabled={isGenerating}
                  >
                    Regenerate
                  </Button>
                </div>

                {generatedPortrait.is_approved && (
                  <div className="mt-4 p-3 bg-success-50 dark:bg-success-900/20 rounded-lg text-center">
                    <p className="text-sm text-success-700 dark:text-success-300">
                      Character approved! Click Continue when ready.
                    </p>
                  </div>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Navigation Buttons */}
      <div className="flex justify-between mt-8">
        <Button variant="flat" onPress={onBack}>
          Back
        </Button>
        <Button
          color="primary"
          size="lg"
          onPress={onContinue}
          isDisabled={!canContinue}
        >
          Continue to Story Writing
        </Button>
      </div>
    </div>
  );
};

export default CharacterCreationStep;
