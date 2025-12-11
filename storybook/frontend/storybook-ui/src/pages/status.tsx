import { useEffect, useState } from 'react';

import { useUserContext } from '@/hooks/userContext';
import { useAxios } from '@/hooks/axiosContext';
import DefaultLayout from "@/layouts/default";
import { checkHealth } from '@/apis/healthCheck';

export default function StatusPage() {
    const { axiosInstance } = useAxios();
    const [healthStatus, setHealthStatus] = useState('');
    const { currentUser, isAuthenticated } = useUserContext();

    useEffect(() => {
        const fetchHealthStatus = async () => {
            const data = await checkHealth(axiosInstance);
            setHealthStatus(data.status);
        };
        fetchHealthStatus();
    }, [isAuthenticated, axiosInstance]);

    return (
        <DefaultLayout>
            <section className="flex flex-col items-center justify-center gap-4 py-8 md:py-10">
                <div className="inline-block max-w-lg text-center justify-center">
                    <h1>Status</h1>
                </div>
                <div>
                    <p>API Health Status: {healthStatus}</p>
                    <p>User Name: {currentUser?.name}</p>
                    <p>User Email: {currentUser?.email}</p>
                </div>
            </section>
        </DefaultLayout>
    );
}
