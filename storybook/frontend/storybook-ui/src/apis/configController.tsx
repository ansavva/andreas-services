import { AxiosInstance } from "axios";

export interface StylePresetsResponse {
    presets: string[];
    default: string;
}

export const getStylePresets = async (axiosInstance: AxiosInstance): Promise<StylePresetsResponse> => {
    const response = await axiosInstance.get<StylePresetsResponse>("/api/config/style-presets");
    return response.data;
};
