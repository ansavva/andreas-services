import React, { useEffect, useState } from "react";
import { Card, CardBody, Button, Textarea } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTrash } from "@fortawesome/free-solid-svg-icons";
import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";
import { updateModelProject } from "@/apis/modelProjectController";

type ModelProjectSettingsStepProps = {
  project: any;
  onDeleteProject?: () => void;
  onProjectUpdated?: (project: any) => void;
};

const ModelProjectSettingsStep: React.FC<ModelProjectSettingsStepProps> = ({
  project,
  onDeleteProject,
  onProjectUpdated,
}) => {
  const { axiosInstance } = useAxios();
  const { showSuccess, showError } = useToast();
  const [description, setDescription] = useState(project?.subject_description || "");
  const [isSaving, setIsSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setDescription(project?.subject_description || "");
    setDirty(false);
  }, [project?.id, project?.subject_description]);

  const handleSaveDescription = async () => {
    if (!project?.id) return;
    setIsSaving(true);
    try {
      const updated = await updateModelProject(axiosInstance, project.id, {
        subjectDescription: description,
      });
      showSuccess("Subject description updated");
      setDirty(false);
      onProjectUpdated?.(updated);
    } catch (error) {
      console.error("Failed to update project description", error);
      showError("Failed to update subject description. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  if (!project) {
    return null;
  }

  return (
    <Card>
      <CardBody className="space-y-4">
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Project Name
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {project?.name || "Untitled"}
          </p>
        </div>

        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Subject
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {project?.subject_name || "Not specified"}
          </p>
        </div>

        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Subject Description
          </p>
          <Textarea
            placeholder="Describe details about the subject to improve prompting"
            minRows={10}
            value={description}
            onValueChange={(value) => {
              setDescription(value);
              setDirty(value !== (project?.subject_description || ""));
            }}
          />
          <Button
            className="mt-2"
            color="primary"
            isDisabled={!dirty || isSaving}
            isLoading={isSaving}
            onPress={handleSaveDescription}
          >
            Save Description
          </Button>
        </div>

        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Status
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400 capitalize">
            {project?.status?.toLowerCase() || "unknown"}
          </p>
        </div>

        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Model Type
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400 capitalize">
            {project?.model_type?.replace(/_/g, " ") || "unknown"}
          </p>
        </div>

        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <Button
            className="w-full"
            color="danger"
            startContent={<FontAwesomeIcon icon={faTrash} />}
            variant="flat"
            onPress={onDeleteProject}
          >
            Delete Project
          </Button>
        </div>
      </CardBody>
    </Card>
  );
};

export default ModelProjectSettingsStep;
