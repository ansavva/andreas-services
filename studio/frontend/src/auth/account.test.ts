import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The two Cognito calls behind "Change email", against a stubbed `fetch`.
 *
 * What these pin: the operation each step names, that the access token — not
 * the ID token — is what goes on the wire, that the swap is followed by a
 * token refresh so the menu says the new address, and that the one failure a
 * person cannot decode from Cognito's wording (a session predating the scope)
 * is told to sign in again.
 */

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() {
      return map.size;
    },
  } as Storage;
}

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
  vi.stubGlobal("sessionStorage", memoryStorage());
  vi.stubGlobal("localStorage", memoryStorage());
  vi.stubGlobal("window", { location: { origin: "http://localhost:5173" } });
  localStorage.setItem(
    "studio.auth.tokens",
    JSON.stringify({
      idToken: "id.old",
      accessToken: "access.old",
      refreshToken: "refresh.old",
      expiresAt: Date.now() + 60_000,
    }),
  );
  vi.resetModules();
  return import("./account");
}

describe("requestEmailChange", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("calls UpdateUserAttributes on the pool's regional endpoint with the access token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        CodeDeliveryDetailsList: [{ Destination: "n***@e***.com" }],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { requestEmailChange } = await loadModule();

    const sentTo = await requestEmailChange("new@example.com");

    expect(sentTo).toBe("n***@e***.com");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://cognito-idp.us-east-1.amazonaws.com/");
    expect((init.headers as Record<string, string>)["X-Amz-Target"]).toBe(
      "AWSCognitoIdentityProviderService.UpdateUserAttributes",
    );
    expect(JSON.parse(init.body as string)).toEqual({
      AccessToken: "access.old",
      UserAttributes: [{ Name: "email", Value: "new@example.com" }],
    });
  });

  it("tells a session from before the scope to sign in again", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          __type: "NotAuthorizedException",
          message: "Access Token does not have required scopes",
        }),
      ),
    );
    const { requestEmailChange } = await loadModule();

    await expect(requestEmailChange("new@example.com")).rejects.toThrow(
      /sign back in/i,
    );
  });
});

describe("confirmEmailChange", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("verifies the code, then refreshes so the stored ID token carries the new address", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, {}))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          id_token: "id.new",
          access_token: "access.new",
          expires_in: 3600,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { confirmEmailChange } = await loadModule();

    await confirmEmailChange(" 123456 ");

    const [, verify] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((verify.headers as Record<string, string>)["X-Amz-Target"]).toBe(
      "AWSCognitoIdentityProviderService.VerifyUserAttribute",
    );
    expect(JSON.parse(verify.body as string)).toEqual({
      AccessToken: "access.old",
      AttributeName: "email",
      Code: "123456",
    });
    const [refreshUrl] = fetchMock.mock.calls[1] as [string];
    expect(refreshUrl).toBe(
      "https://studio-auth.andreas.services/oauth2/token",
    );
    const stored = JSON.parse(localStorage.getItem("studio.auth.tokens")!) as {
      idToken: string;
    };
    expect(stored.idToken).toBe("id.new");
  });

  it("surfaces a wrong code in plain words and refreshes nothing", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(400, {
          __type: "CodeMismatchException",
          message: "Invalid verification code provided",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { confirmEmailChange } = await loadModule();

    await expect(confirmEmailChange("000000")).rejects.toThrow(/not right/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
