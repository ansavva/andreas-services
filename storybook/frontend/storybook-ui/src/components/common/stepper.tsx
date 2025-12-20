// Stepper.tsx
import React from "react";

type Step = {
  title: string;
  description: string;
};

type StepperProps = {
  steps: Step[];
  currentStep: number;
};
const Stepper: React.FC<StepperProps> = ({ steps, currentStep }) => {
  return (
    <ol className="items-center w-full space-y-4 sm:flex sm:space-x-8 sm:space-y-0 rtl:space-x-reverse">
      {steps.map((step, index) => {
        const isActive = index === currentStep;
        const isCompleted = index < currentStep;
        const stepClass = isActive
          ? "text-blue-600 dark:text-blue-500 border-blue-600 dark:border-blue-500"
          : isCompleted
          ? "text-green-600 dark:text-green-500 border-green-600 dark:border-green-500"
          : "text-gray-500 dark:text-gray-400 border-gray-500 dark:border-gray-400";

        return (
          <li key={index} className={`flex items-center ${stepClass} space-x-2.5 rtl:space-x-reverse`}>
            <span className={`flex items-center justify-center w-8 h-8 border rounded-full shrink-0 ${stepClass}`}>
              {isCompleted ? "✓" : index + 1}
            </span>
            <span>
              <h3 className="font-medium leading-tight">{step.title}</h3>
              <p className="text-sm">{step.description}</p>
            </span>
          </li>
        );
      })}
    </ol>
  );
};

export default Stepper;