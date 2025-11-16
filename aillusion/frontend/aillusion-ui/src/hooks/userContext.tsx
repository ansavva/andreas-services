import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useAuth0, User } from '@auth0/auth0-react';

// Define the shape of your context state
interface UserContextType {
  currentUser: User | undefined;
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
  const { user, isAuthenticated, isLoading } = useAuth0();
  const [currentUser, setCurrentUser] = useState<User | undefined>(undefined);

  useEffect(() => {
    if (isAuthenticated && !isLoading) {
      setCurrentUser(user);
    } else {
      setCurrentUser(undefined);
    }
  }, [user, isAuthenticated, isLoading]);

  return (
    <UserContext.Provider value={{ currentUser, isAuthenticated, isLoading }}>
      {children}
    </UserContext.Provider>
  );
};

// Create a hook to use the UserContext
export const useUserContext = () => useContext(UserContext);
