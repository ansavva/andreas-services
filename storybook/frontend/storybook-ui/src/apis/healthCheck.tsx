import { AxiosInstance } from "axios";

export const checkHealth = async (axiosInstance: AxiosInstance) => {
  try {
    const response = await axiosInstance.get('/health');
    return response.data;
  } catch (error) {
    console.error('Error fetching health status:', error);
    return { status: 'unhealthy' };
  }
};
