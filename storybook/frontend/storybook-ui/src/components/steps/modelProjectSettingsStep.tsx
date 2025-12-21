import React from "react";
import { Card, CardBody, Button } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTrash } from "@fortawesome/free-solid-svg-icons";

type ModelProjectSettingsStepProps = {
  project: any;
  onDeleteProject?: () => void;
};

const ModelProjectSettingsStep: React.FC<ModelProjectSettingsStepProps> = ({
  project,
  onDeleteProject,
}) => {
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
