import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardBody } from '@heroui/react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBookOpen, faHome } from '@fortawesome/free-solid-svg-icons';
import DefaultLayout from '@/layouts/default';

const NotFound: React.FC = () => {
  const navigate = useNavigate();

  return (
    <DefaultLayout>
      <div className="flex items-center justify-center min-h-[70vh] px-4">
        <Card className="max-w-md w-full">
          <CardBody className="text-center py-12 px-6">
            <div className="mb-6">
              <FontAwesomeIcon
                icon={faBookOpen}
                className="text-6xl text-default-300"
              />
            </div>

            <h1 className="text-4xl font-bold mb-2">404</h1>
            <h2 className="text-xl font-semibold mb-4">Page Not Found</h2>

            <p className="text-default-500 mb-8">
              The page you're looking for doesn't exist or may have been moved.
            </p>

            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                color="primary"
                size="lg"
                onPress={() => navigate('/')}
                startContent={<FontAwesomeIcon icon={faHome} />}
              >
                Go Home
              </Button>
              <Button
                variant="flat"
                size="lg"
                onPress={() => navigate('/projects')}
              >
                View Projects
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </DefaultLayout>
  );
};

export default NotFound;
