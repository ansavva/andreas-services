import React, { useState, useEffect } from "react";
import { Button, Input, Checkbox, Card, CardBody } from "@heroui/react";

type KidSetupStepProps = {
  projectId: string;
  onComplete: (data: KidSetupData) => void;
  loading: boolean;
  initialData?: {
    childName?: string;
    childAge?: number;
    consentGiven?: boolean;
  };
};

export type KidSetupData = {
  childName: string;
  childAge: number;
  consentGiven: boolean;
};

const KidSetupStep: React.FC<KidSetupStepProps> = ({
  projectId,
  onComplete,
  loading,
  initialData,
}) => {
  const [childName, setChildName] = useState(initialData?.childName || "");
  const [childAge, setChildAge] = useState<string>(initialData?.childAge?.toString() || "");
  const [consentGiven, setConsentGiven] = useState(initialData?.consentGiven || false);

  // Update state when initialData changes (e.g., when going back to this step)
  useEffect(() => {
    if (initialData) {
      setChildName(initialData.childName || "");
      setChildAge(initialData.childAge?.toString() || "");
      setConsentGiven(initialData.consentGiven || false);
    }
  }, [initialData]);
  const [errors, setErrors] = useState<{
    childName?: string;
    childAge?: string;
    consent?: string;
  }>({});

  const validate = (): boolean => {
    const newErrors: typeof errors = {};

    if (!childName.trim()) {
      newErrors.childName = "Child's name is required";
    }

    const age = parseInt(childAge);
    if (!childAge || isNaN(age)) {
      newErrors.childAge = "Age is required";
    } else if (age < 0 || age > 12) {
      newErrors.childAge = "Age must be between 0 and 12";
    }

    if (!consentGiven) {
      newErrors.consent = "Consent is required to continue";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleContinue = () => {
    if (validate()) {
      onComplete({
        childName: childName.trim(),
        childAge: parseInt(childAge),
        consentGiven,
      });
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h3 className="text-2xl font-bold mb-2">Tell Us About Your Child</h3>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        We'll create a personalized story featuring your child as the main character!
      </p>

      <Card className="mb-6">
        <CardBody className="gap-4">
          <Input
            label="Child's Name"
            placeholder="Enter your child's name"
            value={childName}
            onChange={(e) => setChildName(e.target.value)}
            isInvalid={!!errors.childName}
            errorMessage={errors.childName}
            isRequired
            variant="bordered"
          />

          <Input
            type="number"
            label="Child's Age"
            placeholder="Enter age (0-12)"
            value={childAge}
            onChange={(e) => setChildAge(e.target.value)}
            isInvalid={!!errors.childAge}
            errorMessage={errors.childAge}
            isRequired
            variant="bordered"
            min={0}
            max={12}
          />

          <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg">
            <h4 className="font-semibold mb-2">Privacy & Safety</h4>
            <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
              Your child's information and photos are securely stored and used
              only to create personalized stories. We never share this data
              with third parties.
            </p>
            <Checkbox
              isSelected={consentGiven}
              onValueChange={setConsentGiven}
              isInvalid={!!errors.consent}
            >
              <span className="text-sm">
                I am the parent/guardian or have permission to upload and
                process these images for story creation
              </span>
            </Checkbox>
            {errors.consent && (
              <p className="text-tiny text-danger mt-1">{errors.consent}</p>
            )}
          </div>
        </CardBody>
      </Card>

      <div className="flex justify-end">
        <Button
          color="primary"
          size="lg"
          onPress={handleContinue}
          isLoading={loading}
          isDisabled={loading}
        >
          Continue to Photo Upload
        </Button>
      </div>
    </div>
  );
};

export default KidSetupStep;
