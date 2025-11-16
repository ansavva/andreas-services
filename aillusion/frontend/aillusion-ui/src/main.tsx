import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Auth0Provider } from '@auth0/auth0-react';
import { UserProvider } from '@/hooks/userContext.tsx';
import { AxiosProvider } from "./hooks/axiosContext.tsx";

import App from "./app.tsx";
import { Provider } from "./provider.tsx";
import "@/styles/globals.css";

const domain = import.meta.env.VITE_AUTH0_DOMAIN;
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Provider>
      <Auth0Provider
        domain={domain}
        clientId={clientId}
        cacheLocation="localstorage"
        useRefreshTokens={true}
        authorizationParams={{ 
          redirect_uri: window.location.origin, 
          audience: "https://aillusion-api" 
        }}
      >
        <UserProvider>
          <AxiosProvider>
            <App />
          </AxiosProvider>
        </UserProvider>
      </Auth0Provider>
      </Provider>
    </BrowserRouter>
  </React.StrictMode>,
);
