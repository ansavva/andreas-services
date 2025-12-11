import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { getCurrentUser, fetchUserAttributes, AuthUser } from 'aws-amplify/auth';

// Define user type based on Cognito attributes
interface CognitoUser {
  username: string;
  userId: string;
  email?: string;
  name?: string;
  picture?: string;
  [key: string]: any;
}

// Define the shape of your context state
interface UserContextType {
  currentUser: CognitoUser | undefined;
  isAuthenticated: boolean;
  isLoading: boolean;
}

// Create context with default values
const UserContext = createContext<UserContextType>({
  currentUser: undefined,
  isAuthenticated: false,
  isLoading: true,
});

interface UserProviderProps {
  children: ReactNode;
}

// Create the UserProvider component
export const UserProvider = ({ children }: UserProviderProps) => {
  const [currentUser, setCurrentUser] = useState<CognitoUser | undefined>(undefined);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    checkAuthState();
  }, []);

  const checkAuthState = async () => {
    try {
      const user = await getCurrentUser();
      const attributes = await fetchUserAttributes();

      setCurrentUser({
        username: user.username,
        userId: user.userId,
        email: attributes.email,
        name: attributes.name,
        picture: attributes.picture,
        ...attributes
      });
      setIsAuthenticated(true);
    } catch (error) {
      setCurrentUser(undefined);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <UserContext.Provider value={{ currentUser, isAuthenticated, isLoading }}>
      {children}
    </UserContext.Provider>
  );
};

// Create a hook to use the UserContext
export const useUserContext = () => useContext(UserContext);
