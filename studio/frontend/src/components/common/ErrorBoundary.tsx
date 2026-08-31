import { Component, type ErrorInfo, type ReactNode } from "react";

import { Alert, Button, Text } from "@ansavva/design-system";

/**
 * The last thing between a thrown render and a white page.
 *
 * **React unmounts the whole tree when a render throws**, and with nothing to
 * catch it the app becomes a blank document — no message, no address, nothing to
 * report. That is not a rare state to design for: it is what every one of this
 * app's bugs looks like from the outside, and it is indistinguishable from a
 * network stall or a dead session.
 *
 * So this catches, says what broke, and keeps the URL — which is the one piece
 * of evidence worth having, because it names the record that did it.
 *
 * A class, because `getDerivedStateFromError` has no hook equivalent; there is
 * no way to write this with function components.
 *
 * **It deliberately does not swallow.** The error goes to the console as well,
 * so a session with devtools open still gets the stack, and the message shown
 * here is the same string a report would quote.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  /**
   * Clear on a history move, which is what made `Go back` look dead.
   *
   * `history.back()` changes the address and React Router renders the previous
   * route — but this boundary is ABOVE the router and its `error` was never
   * cleared, so it went on drawing the same error screen over a route that had
   * already changed. The URL moved and the page did not.
   *
   * Safe to clear here in a way it is not on a button, for the reason the
   * `Reload` comment gives: what threw is only still in the tree if the route
   * is the same one, and a `popstate` means it is not.
   */
  componentDidMount() {
    window.addEventListener("popstate", this.clear);
  }

  componentWillUnmount() {
    window.removeEventListener("popstate", this.clear);
  }

  clear = () => this.setState({ error: null });

  goBack = () => {
    // A pasted or bookmarked address has nothing behind it, so `back()` is a
    // no-op and no `popstate` ever fires — the button would read as dead for a
    // second reason. Home is somewhere.
    if (window.history.length > 1) window.history.back();
    else window.location.assign("/");
  };

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept out of the UI and in the console: a component stack is for whoever is
    // debugging, and putting it on the page would bury the one line that says
    // what happened.
    console.error("A page failed to render", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col gap-4 p-6">
        <Alert.Root intent="danger">
          <Alert.Title>This page could not be drawn</Alert.Title>
          <Alert.Description>
            Something in the page threw while rendering. The rest of the app is fine — the
            address below is what failed.
          </Alert.Description>
        </Alert.Root>

        <div className="flex flex-col gap-1">
          <Text variant="caption" tone="muted">
            What broke
          </Text>
          <pre
            className="max-h-64 overflow-auto rounded-none bg-surface-alt p-2 text-xs
                       whitespace-pre-wrap text-muted"
          >
            {error.message || String(error)}
          </pre>
        </div>

        <div className="flex flex-col gap-1">
          <Text variant="caption" tone="muted">
            Where
          </Text>
          <pre className="overflow-x-auto rounded-none bg-surface-alt p-2 text-xs text-muted">
            {window.location.pathname}
          </pre>
        </div>

        <div className="flex flex-wrap gap-2">
          {/* A full reload rather than `setState({error: null})`: whatever threw
              is still in the tree's props, so re-rendering it throws again and
              the button looks broken. */}
          <Button intent="primary" size="sm" onClick={() => window.location.reload()}>
            Reload
          </Button>
          <Button intent="secondary" size="sm" onClick={this.goBack}>
            Go back
          </Button>
        </div>
      </div>
    );
  }
}
