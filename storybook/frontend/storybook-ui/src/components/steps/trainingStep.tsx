// TrainingStep.tsx
import React from "react";

type TrainingStepProps = {
  trainingStatus: string;
};
const TrainingStep: React.FC<TrainingStepProps> = ({ trainingStatus }) => {
  return (
    <div className="flex flex-col items-center">
      <div className="loading mt-5 mb-3">
        <div className="dot" />
        <div className="dot" />
        <div className="dot" />
        <div className="dot" />
        <div className="dot" />
      </div>
      {(trainingStatus === "pending" || trainingStatus === "processing") && (
        <p className="text-2xl mt-3">
          Training is in progress. This could take awhile! Don't leave this
          screen.
        </p>
      )}
      {trainingStatus === "succeeded" && (
        <p className="text-2xl mt-3">Training completed successfully!</p>
      )}
      {trainingStatus === "failed" && (
        <p className="text-2xl mt-3">Training failed. Please try again.</p>
      )}
    </div>
  );
};

export default TrainingStep;
