import React, { useState } from "react";
import { Button, Card, CardBody, Input } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faArrowRight } from "@fortawesome/free-solid-svg-icons";
import { useAxios } from "@/hooks/axiosContext";
import { createModelProject, updateModelProject } from "@/apis/modelProjectController";
import { useToast } from "@/hooks/useToast";
import { getErrorMessage, logError } from "@/utils/errorHandling";

type SubjectSetupStepProps = {
  projectId: string;
  project: any;
  onProjectCreated: (project: any) => void;
  onComplete: () => void;
};

const SubjectSetupStep: React.FC<SubjectSetupStepProps> = ({
  projectId,
  project,
  onProjectCreated,
  onComplete,
}) => {
  const { axiosInstance } = useAxios();
  const { showError, showSuccess } = useToast();

  const [subjectName, setSubjectName] = useState(project?.subject_name || "");
  const [subjectNameError, setSubjectNameError] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const handleContinue = async () => {
    if (!subjectName.trim()) {
      setSubjectNameError("Subject name is required");
      return;
    }
    setSubjectNameError("");

    setIsCreating(true);
    try {
      if (projectId === "new") {
        // Create new project
        const newProject = await createModelProject(axiosInstance, subjectName, subjectName);
        onProjectCreated(newProject);
        showSuccess("Project created successfully!");
      } else if (project && subjectName !== project.subject_name) {
        // Update existing project if subject name changed
        const updatedProject = await updateModelProject(axiosInstance, projectId, {
          name: subjectName,
          subjectName: subjectName,
        });
        onProjectCreated(updatedProject);
        showSuccess("Subject name updated successfully!");
      }
      onComplete();
    } catch (error: any) {
      logError("Save project", error);
      showError(getErrorMessage(error, "Failed to save project. Please try again."));
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
            label="Subject Name"
            placeholder="e.g., John, My Dog, Sarah, etc."
            value={subjectName}
            onValueChange={(value) => {
              setSubjectName(value);
              if (value.trim()) setSubjectNameError("");
            }}
            isInvalid={!!subjectNameError}
            errorMessage={subjectNameError}
            isRequired
            variant="bordered"
            size="lg"
            description="This is the person or thing you'll be training the AI model to recognize"
            className="mb-6"
          />

          <Button
            color="primary"
            size="lg"
            className="w-full"
            endContent={<FontAwesomeIcon icon={faArrowRight} />}
            onPress={handleContinue}
            isLoading={isCreating}
            isDisabled={!subjectName.trim() || isCreating}
          >
            {isCreating ? "Creating Project..." : "Continue"}
          </Button>
        </CardBody>
      </Card>
    </div>
  );
};

export default SubjectSetupStep;
