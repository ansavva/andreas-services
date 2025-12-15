import { useEffect } from 'react';
import { Outlet } from "react-router-dom";
import { signInWithRedirect } from 'aws-amplify/auth';
import { useUserContext } from '@/hooks/userContext';

const PrivateRoute = () => {
  const { isAuthenticated, isLoading } = useUserContext();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      // Redirect to Cognito hosted UI for login
      signInWithRedirect();
    }
  }, [isAuthenticated, isLoading]);

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (!isAuthenticated) {
    return null;
  }

  return <Outlet />;
};

export default PrivateRoute;
