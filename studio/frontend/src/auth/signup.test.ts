import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The two Cognito calls behind "Create an account", against a stubbed `fetch`.
 *
 * What these pin: that the invite code travels as `ClientMetadata.invite_code`
 * — the one key the pool's pre-sign-up trigger reads — and not as an
 * attribute; that no token goes on the wire, because there is none yet; and
 * that the gate's refusal reaches the person without Cognito's
 * "PreSignUp failed with error" prefix.
 */

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/x-amz-json-1.1" },
  });
}

async function loadModule() {
  vi.stubEnv("VITE_COGNITO_DOMAIN", "studio-auth.andreas.services");
  vi.stubEnv("VITE_COGNITO_CLIENT_ID", "test-client-id");
  vi.stubEnv("VITE_COGNITO_USER_POOL_ID", "us-east-1_TestPool");
  vi.resetModules();
  return import("./signup");
}

describe("signUp", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("sends the invite code as ClientMetadata, with the public client id and no token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { CodeDeliveryDetails: { Destination: "n***@e***.com" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { signUp } = await loadModule();

    const sentTo = await signUp("new@example.com", "Correct-horse-1", "open-sesame");

    expect(sentTo).toBe("n***@e***.com");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://cognito-idp.us-east-1.amazonaws.com/");
    expect((init.headers as Record<string, string>)["X-Amz-Target"]).toBe(
      "AWSCognitoIdentityProviderService.SignUp",
    );
    expect(JSON.parse(init.body as string)).toEqual({
      ClientId: "test-client-id",
      Username: "new@example.com",
      Password: "Correct-horse-1",
      UserAttributes: [{ Name: "email", Value: "new@example.com" }],
      ClientMetadata: { invite_code: "open-sesame" },
    });
  });

  it("passes the gate's refusal through without Cognito's prefix", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          __type: "UserLambdaValidationException",
          message:
            "PreSignUp failed with error Studio is invite-only. Sign up with an invite code.",
        }),
      ),
    );
    const { signUp } = await loadModule();

    await expect(signUp("new@example.com", "Correct-horse-1", "wrong")).rejects.toThrow(
      "Studio is invite-only. Sign up with an invite code.",
    );
  });

  it("points an existing address at sign-in", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(400, { __type: "UsernameExistsException" })),
    );
    const { signUp } = await loadModule();

    await expect(signUp("old@example.com", "Correct-horse-1", "open-sesame")).rejects.toThrow(
      /sign in instead/i,
    );
  });
});

describe("confirmSignUp", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("calls ConfirmSignUp with the trimmed code", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    const { confirmSignUp } = await loadModule();

    await confirmSignUp("new@example.com", " 424242 ");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Amz-Target"]).toBe(
      "AWSCognitoIdentityProviderService.ConfirmSignUp",
    );
    expect(JSON.parse(init.body as string)).toEqual({
      ClientId: "test-client-id",
      Username: "new@example.com",
      ConfirmationCode: "424242",
    });
  });

  it("says when the code is wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(400, { __type: "CodeMismatchException" })),
    );
    const { confirmSignUp } = await loadModule();

    await expect(confirmSignUp("new@example.com", "000000")).rejects.toThrow(/not right/);
  });
});
