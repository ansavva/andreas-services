import { useEffect, useMemo, useState } from "react";
import { Button, Card, CardBody, Spinner, Modal, ModalContent, ModalHeader, ModalBody, ModalFooter } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTrash } from "@fortawesome/free-solid-svg-icons";

import DefaultLayout from "@/layouts/default";
import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";
import { deleteImage, getImageUsage, listGeneratedImages } from "@/apis/imageController";
import ImageGrid from "@/components/images/imageGrid";
import { getErrorMessage } from "@/utils/errorHandling";

type GeneratedImage = {
  id: string;
  project_id: string;
  project_name?: string | null;
  filename?: string;
  content_type?: string;
  size_bytes?: number;
  processing?: boolean;
  created_at?: string;
};

type ImageUsage = {
  generation_histories: Array<{
    id: string;
    project_id: string;
    prompt: string;
    status: string;
    created_at: string | null;
  }>;
  training_runs: Array<{
    id: string;
    project_id: string;
    status: string;
    created_at: string | null;
  }>;
};

export default function ImagesPage() {
  const { axiosInstance } = useAxios();
  const { showError, showSuccess } = useToast();
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [loading, setLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(false);
  const [selectedImage, setSelectedImage] = useState<GeneratedImage | null>(null);
  const [usage, setUsage] = useState<ImageUsage | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const loadImages = async () => {
    setLoading(true);
    try {
      const response = await listGeneratedImages(axiosInstance);
      setImages(response.images || []);
    } catch (err) {
      showError(getErrorMessage(err, "Failed to load generated images."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadImages();
  }, []);

  const handleDeleteClick = async (image: GeneratedImage) => {
    setSelectedImage(image);
    setUsage(null);
    setDeleteOpen(true);
    setUsageLoading(true);
    try {
      const data = await getImageUsage(axiosInstance, image.id);
      setUsage(data);
    } catch (err) {
      showError(getErrorMessage(err, "Failed to load image usage."));
    } finally {
      setUsageLoading(false);
    }
  };

  const confirmDelete = async () => {
    if (!selectedImage) return;
    try {
      await deleteImage(axiosInstance, selectedImage.id);
      setImages((prev) => prev.filter((img) => img.id !== selectedImage.id));
      showSuccess("Image deleted.");
      setDeleteOpen(false);
      setSelectedImage(null);
    } catch (err) {
      showError(getErrorMessage(err, "Failed to delete image."));
    }
  };

  const usageSummary = useMemo(() => {
    const historyCount = usage?.generation_histories.length || 0;
    const trainingCount = usage?.training_runs.length || 0;
    return { historyCount, trainingCount };
  }, [usage]);

  return (
    <DefaultLayout>
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-4xl font-bold">Images</h1>
            <p className="text-gray-600 dark:text-gray-400">
              Manage your generated images across projects.
            </p>
          </div>
          <Button variant="flat" onPress={loadImages} isDisabled={loading}>
            Refresh
          </Button>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : images.length === 0 ? (
          <Card>
            <CardBody className="text-sm text-gray-600 dark:text-gray-400">
              No generated images yet.
            </CardBody>
          </Card>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {images.map((image) => (
              <Card key={image.id}>
                <CardBody className="flex flex-col gap-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm text-gray-500">Project</p>
                      <p className="font-semibold">
                        {image.project_name || image.project_id}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {image.created_at
                          ? new Date(image.created_at).toLocaleString()
                          : "Unknown date"}
                      </p>
                    </div>
                    <Button
                      color="danger"
                      variant="flat"
                      startContent={<FontAwesomeIcon icon={faTrash} />}
                      onPress={() => handleDeleteClick(image)}
                    >
                      Delete
                    </Button>
                  </div>
                  <ImageGrid
                    images={[{ id: image.id, processing: image.processing }]}
                    showModal
                    thumbnailWidth={220}
                    thumbnailHeight={220}
                  />
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Modal isOpen={deleteOpen} onClose={() => setDeleteOpen(false)} size="lg">
        <ModalContent>
          <ModalHeader>Delete Image</ModalHeader>
          <ModalBody className="space-y-4">
            {selectedImage && (
              <ImageGrid
                images={[{ id: selectedImage.id, processing: selectedImage.processing }]}
                showModal={false}
                thumbnailWidth={180}
                thumbnailHeight={180}
              />
            )}
            {usageLoading ? (
              <div className="flex justify-center py-4">
                <Spinner size="sm" />
              </div>
            ) : (
              <div className="text-sm text-gray-600 dark:text-gray-400 space-y-2">
                <p>
                  This image is referenced in {usageSummary.historyCount} generation
                  {usageSummary.historyCount === 1 ? "" : "s"} and {usageSummary.trainingCount} training
                  {usageSummary.trainingCount === 1 ? "" : " runs"}.
                </p>
                {usageSummary.historyCount > 0 && (
                  <p>
                    Deleting it will break those history entries.
                  </p>
                )}
                {usageSummary.trainingCount > 0 && (
                  <p>
                    Deleting it will break those training runs.
                  </p>
                )}
              </div>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="light" onPress={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button color="danger" onPress={confirmDelete} isDisabled={usageLoading}>
              Delete Image
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </DefaultLayout>
  );
}
