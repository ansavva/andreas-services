import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Amplify } from 'aws-amplify';
import { UserProvider } from '@/hooks/userContext.tsx';
import { AxiosProvider } from "./hooks/axiosContext.tsx";
import { ToastProvider } from "./hooks/useToast.tsx";

import App from "./app.tsx";
import { Provider } from "./provider.tsx";
import "@/styles/globals.css";

// Configure Amplify
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_AWS_COGNITO_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_AWS_COGNITO_APP_CLIENT_ID,
      loginWith: {
        oauth: {
          domain: import.meta.env.VITE_AWS_COGNITO_DOMAIN,
          scopes: ['openid', 'email', 'profile'],
          redirectSignIn: [window.location.origin + "/app"],
          redirectSignOut: [window.location.origin + "/app"],
          responseType: 'code'
        }
      }
    }
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename="/app">
      <Provider>
        <ToastProvider>
          <UserProvider>
            <AxiosProvider>
              <App />
            </AxiosProvider>
          </UserProvider>
        </ToastProvider>
      </Provider>
    </BrowserRouter>
  </React.StrictMode>,
);
