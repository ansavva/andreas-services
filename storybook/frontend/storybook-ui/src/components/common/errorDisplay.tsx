import React from "react";
import { Card, CardBody, Button } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faExclamationTriangle,
  faRefresh,
} from "@fortawesome/free-solid-svg-icons";

interface ErrorDisplayProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryText?: string;
}

const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  title = "Something went wrong",
  message,
  onRetry,
  retryText = "Try Again",
}) => {
  return (
    <Card className="max-w-md mx-auto mt-8">
      <CardBody className="text-center py-8 px-6">
        <div className="mb-4">
          <FontAwesomeIcon
            className="text-5xl text-warning"
            icon={faExclamationTriangle}
          />
        </div>

        <h3 className="text-xl font-semibold mb-2">{title}</h3>
        <p className="text-default-500 mb-6">{message}</p>

        {onRetry && (
          <Button
            color="primary"
            startContent={<FontAwesomeIcon icon={faRefresh} />}
            variant="flat"
            onPress={onRetry}
          >
            {retryText}
          </Button>
        )}
      </CardBody>
    </Card>
  );
};

export default ErrorDisplay;
