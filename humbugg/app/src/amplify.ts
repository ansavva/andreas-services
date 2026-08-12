// Amplify's React Native wiring. IMPORT THIS BEFORE ANYTHING FROM `aws-amplify`
// — the root layout does, which is why it is the first import there.
//
// `aws-amplify` is written against browser globals. Three of them do not exist
// on a device and each one fails differently and late:
//
//   react-native-get-random-values  crypto.getRandomValues — SRP generates a
//                                   random large integer per sign-in, so
//                                   without it auth throws on the first login
//                                   rather than at startup.
//   react-native-url-polyfill       URL / URLSearchParams, which Amplify's
//                                   endpoint resolution builds on.
//   @aws-amplify/react-native       the RN adapter itself; `cognitoUserPoolsTokenProvider`
//                                   below then persists tokens with AsyncStorage
//                                   instead of localStorage, so a session
//                                   survives an app restart.
//
// All three are side-effect imports with no exports, so import ORDER is the
// whole contract: they must run before `Amplify.configure`.
import 'react-native-get-random-values';
import 'react-native-url-polyfill/auto';
import '@aws-amplify/react-native';

import AsyncStorage from '@react-native-async-storage/async-storage';
import { Amplify } from 'aws-amplify';
import { cognitoUserPoolsTokenProvider } from 'aws-amplify/auth/cognito';
import { defaultStorage } from 'aws-amplify/utils';
import { Platform } from 'react-native';

// Read as three separate static lookups: Metro substitutes `process.env.EXPO_PUBLIC_X`
// textually, so a computed key would inline as `undefined`.
const userPoolId = process.env.EXPO_PUBLIC_COGNITO_USER_POOL_ID ?? '';
const userPoolClientId = process.env.EXPO_PUBLIC_COGNITO_CLIENT_ID ?? '';
export const AWS_REGION = process.env.EXPO_PUBLIC_AWS_REGION ?? 'us-east-1';

/**
 * Whether a user pool was configured at build time. False in a bare checkout
 * with no `.env.local`, and the auth context uses it to settle into "signed
 * out" instead of hanging on a session fetch that can only throw.
 */
export const isAuthConfigured = Boolean(userPoolId && userPoolClientId);

if (isAuthConfigured) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
        loginWith: { email: true },
        signUpVerificationMethod: 'code',
        userAttributes: { email: { required: true } },
      },
    },
  });

  // On web, Amplify's own default (localStorage) is right and AsyncStorage is a
  // localStorage shim anyway; setting it there would only add a layer.
  if (Platform.OS !== 'web') {
    cognitoUserPoolsTokenProvider.setKeyValueStorage(AsyncStorage);
  } else {
    cognitoUserPoolsTokenProvider.setKeyValueStorage(defaultStorage);
  }
}
