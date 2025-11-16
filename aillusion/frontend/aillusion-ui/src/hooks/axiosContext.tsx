// src/contexts/AxiosContext.tsx

import React, { createContext, useContext } from 'react';
import axios, { AxiosInstance } from 'axios';
import { useAuth0 } from '@auth0/auth0-react';

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
  let token;
  const { getAccessTokenSilently } = useAuth0();

  // Create an Axios instance
  const axiosInstance = axios.create({
    baseURL: import.meta.env.VITE_API_URL, // Replace with your API base URL
  });

  axiosInstance.interceptors.request.use(async (config) => {
    token = await getAccessTokenSilently(); // getting an access token from auth0
    config.headers.Authorization = `Bearer ${token}`; // setting up the access token
    return config;
  });

  return (
    <AxiosContext.Provider value={{ axiosInstance }}>
      {children}
    </AxiosContext.Provider>
  );
};
