import { useAuth0 } from '@auth0/auth0-react';
import { Outlet } from "react-router-dom";

const PrivateRoute = () => {
  const { isAuthenticated, loginWithRedirect, isLoading } = useAuth0();

  if (isLoading) {
    return <div>Loading...</div>;  // Optionally add a loading spinner
  }

  if (!isAuthenticated) {
    loginWithRedirect();
    return null;  // Return null to avoid rendering any elements while redirecting
  }

  return <Outlet />;
};

export default PrivateRoute;
