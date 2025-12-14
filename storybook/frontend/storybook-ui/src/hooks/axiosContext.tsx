// src/contexts/AxiosContext.tsx

import React, { createContext, useContext } from 'react';
import axios, { AxiosInstance } from 'axios';
import { fetchAuthSession } from 'aws-amplify/auth';

// Define the Axios context type
interface AxiosContextType {
  axiosInstance: AxiosInstance;
}

// Create the context with a default value
const AxiosContext = createContext<AxiosContextType | undefined>(undefined);

// Custom hook to use the AxiosContext
export const useAxios = (): AxiosContextType => {
  const context = useContext(AxiosContext);
  if (!context) {
    throw new Error('useAxios must be used within an AxiosProvider');
  }
  return context;
};

// AxiosProvider component
export const AxiosProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Create an Axios instance
  console.log('VITE_API_URL:', import.meta.env.VITE_API_URL); // Debug log
  const axiosInstance = axios.create({
    baseURL: import.meta.env.VITE_API_URL,
  });

  axiosInstance.interceptors.request.use(async (config) => {
    try {
      // Get the current session from Cognito
      const session = await fetchAuthSession();
      // Use access token instead of ID token to avoid at_hash validation issues
      const token = session.tokens?.accessToken?.toString();

      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch (error) {
      console.error('Error fetching auth session:', error);
    }

    return config;
  });

  return (
    <AxiosContext.Provider value={{ axiosInstance }}>
      {children}
    </AxiosContext.Provider>
  );
};
