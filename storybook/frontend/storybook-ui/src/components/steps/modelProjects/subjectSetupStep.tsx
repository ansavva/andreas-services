import React, { useEffect, useState } from "react";
import { Button, Card, CardBody, Input, RadioGroup, Radio } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faArrowRight } from "@fortawesome/free-solid-svg-icons";

import { useAxios } from "@/hooks/axiosContext";
import {
  createModelProject,
  updateModelProject,
  getModelTypes,
} from "@/apis/modelProjectController";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage, logError } from "@/utils/errorHandling";

type SubjectSetupStepProps = {
  projectId: string;
  project: any;
  onProjectCreated: (project: any) => void;
  onComplete: () => void;
};

type ModelTypeOption = {
  id: string;
  label: string;
  description?: string;
};

const SubjectSetupStep: React.FC<SubjectSetupStepProps> = ({
  projectId,
  project,
  onProjectCreated,
  onComplete,
}) => {
  const { axiosInstance } = useAxios();
  const { showError, showSuccess } = useToast();

  const [subjectName, setSubjectName] = useState<string>(project?.subject_name || "");
  const [subjectNameError, setSubjectNameError] = useState<string>("");
  const [modelType, setModelType] = useState<string>(project?.model_type || "");
  const [modelTypes, setModelTypes] = useState<ModelTypeOption[]>([]);
  const [isLoadingModelTypes, setIsLoadingModelTypes] = useState<boolean>(true);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    const loadModelTypes = async () => {
      setIsLoadingModelTypes(true);
      try {
        const response = await getModelTypes(axiosInstance);
        const options: ModelTypeOption[] = response.modelTypes || [];
        setModelTypes(options);
        const fallback =
          project?.model_type ||
          response.defaultModelType ||
          options[0]?.id ||
          "";
        setModelType((current) => current || fallback);
      } catch (error) {
        logError("Load model types", error);
        showError(
          getErrorMessage(error, "Failed to load available model types."),
        );
      } finally {
        setIsLoadingModelTypes(false);
      }
    };

    loadModelTypes();
  }, [axiosInstance, project?.model_type, projectId, showError]);

  const handleContinue = async () => {
    if (!subjectName.trim()) {
      setSubjectNameError("Subject name is required");

      return;
    }
    setSubjectNameError("");

    if (!modelType) {
      showError("No model types are available. Please try again later.");
      return;
    }

    setIsCreating(true);
    try {
      if (projectId === "new") {
        // Create new project
        const newProject = await createModelProject(
          axiosInstance,
          subjectName,
          subjectName,
          modelType,
        );

        onProjectCreated(newProject);
        showSuccess("Project created successfully!");
      } else if (project && subjectName !== project.subject_name) {
        // Update existing project if subject name changed
        const updatedProject = await updateModelProject(
          axiosInstance,
          projectId,
          {
            name: subjectName,
            subjectName: subjectName,
          },
        );

        onProjectCreated(updatedProject);
        showSuccess("Subject name updated successfully!");
      }
      onComplete();
    } catch (error: any) {
      logError("Save project", error);
      showError(
        getErrorMessage(error, "Failed to save project. Please try again."),
      );
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h3 className="text-2xl font-bold mb-2">Subject Information</h3>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Enter the name of the subject you want to train the AI model on.
      </p>

      <Card>
        <CardBody className="p-8">
          <Input
            isRequired
            className="mb-6"
            description="This is the person or thing you'll be training the AI model to recognize"
            errorMessage={subjectNameError}
            isInvalid={!!subjectNameError}
            label="Subject Name"
            placeholder="e.g., John, My Dog, Sarah, etc."
            size="lg"
            value={subjectName}
            variant="bordered"
            onValueChange={(value) => {
              setSubjectName(value);
              if (value.trim()) setSubjectNameError("");
            }}
          />

          {modelTypes.length > 0 ? (
            <RadioGroup
              className="mb-6"
              label="Model Type"
              value={modelType}
              isDisabled={projectId !== "new" || isLoadingModelTypes}
              onValueChange={(value) => setModelType(value as string)}
            >
              {modelTypes.map((type) => (
                <Radio key={type.id} value={type.id} description={type.description}>
                  {type.label}
                </Radio>
              ))}
            </RadioGroup>
          ) : (
            <p className="text-sm text-gray-500 mb-6">
              {isLoadingModelTypes
                ? "Loading model types..."
                : "No model types are currently available."}
            </p>
          )}

          <Button
            className="w-full"
            color="primary"
            endContent={<FontAwesomeIcon icon={faArrowRight} />}
            isDisabled={!subjectName.trim() || !modelType || isCreating}
            isLoading={isCreating}
            size="lg"
            onPress={handleContinue}
          >
            {isCreating ? "Creating Project..." : "Continue"}
          </Button>
        </CardBody>
      </Card>
    </div>
  );
};

export default SubjectSetupStep;
