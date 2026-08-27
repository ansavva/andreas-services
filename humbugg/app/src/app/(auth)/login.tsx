// `/login` is not a page any more, it is the address sign-out lands on.
//
// Cognito's `/logout` sends the browser to a registered `logout_urls` entry, and
// this is humbugg's. It renders no form and no pitch: it starts the hosted flow
// straight away, the same as the protected guard does. Cognito's own session
// cookie is gone by the time anyone arrives, so what they see next is the hosted
// sign-in form rather than a silent round trip back into the app.
import { SignInRedirect } from '../../components/sign-in-redirect';

export default function LoginRoute() {
  return <SignInRedirect />;
}
