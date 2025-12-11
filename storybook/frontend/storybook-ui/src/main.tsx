import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Amplify } from 'aws-amplify';
import { UserProvider } from '@/hooks/userContext.tsx';
import { AxiosProvider } from "./hooks/axiosContext.tsx";

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
          redirectSignIn: [window.location.origin],
          redirectSignOut: [window.location.origin],
          responseType: 'code'
        }
      }
    }
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Provider>
        <UserProvider>
          <AxiosProvider>
            <App />
          </AxiosProvider>
        </UserProvider>
      </Provider>
    </BrowserRouter>
  </React.StrictMode>,
);
