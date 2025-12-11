import { FormEvent, useState } from 'react';
import { useAuth } from '../context/AuthContext';

interface LoginFormState {
  apiBaseUrl: string;
  cognitoDomain: string;
  clientId: string;
  clientSecret: string;
  username: string;
  password: string;
  existingToken: string;
}

const fieldClass =
  'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-200';

const labelClass = 'text-sm font-medium text-slate-700';

export default function LoginPanel() {
  const auth = useAuth();
  const [form, setForm] = useState<LoginFormState>({
    apiBaseUrl: auth.apiBaseUrl,
    cognitoDomain: auth.cognitoDomain,
    clientId: auth.clientId,
    clientSecret: auth.clientSecret,
    username: '',
    password: '',
    existingToken: ''
  });
  const [status, setStatus] = useState<string | null>(null);

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus(null);
    try {
      await auth.loginWithPassword({
        apiBaseUrl: form.apiBaseUrl,
        cognitoDomain: form.cognitoDomain,
        clientId: form.clientId,
        clientSecret: form.clientSecret,
        username: form.username,
        password: form.password
      });
      setStatus('Signed in successfully.');
    } catch (err) {
      if (err instanceof Error) {
        setStatus(err.message);
      } else {
        setStatus('Unable to sign in.');
      }
    }
  };

  const handleUseToken = async () => {
    if (!form.existingToken.trim()) {
      setStatus('Provide an access token first.');
      return;
    }
    try {
      await auth.setTokenManually(form.existingToken.trim(), form.apiBaseUrl);
      setStatus('Token saved.');
    } catch (err) {
      if (err instanceof Error) {
        setStatus(err.message);
      } else {
        setStatus('Unable to use token.');
      }
    }
  };

  return (
    <div className="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 shadow-lg">
      <h1 className="text-3xl font-semibold text-slate-900">Humbugg Access</h1>
      <p className="mt-2 text-sm text-slate-600">
        Connect directly to the Humbugg API by authenticating against your AWS Cognito user pool.
      </p>
      <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelClass}>API base URL</span>
            <input
              type="url"
              required
              name="apiBaseUrl"
              value={form.apiBaseUrl}
              onChange={handleChange}
              className={fieldClass}
              placeholder="http://localhost:5001"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Cognito domain</span>
            <input
              type="url"
              required
              name="cognitoDomain"
              value={form.cognitoDomain}
              onChange={handleChange}
              className={fieldClass}
              placeholder="https://your-domain.auth.us-east-1.amazoncognito.com"
            />
          </label>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Client ID</span>
            <input
              type="text"
              required
              name="clientId"
              value={form.clientId}
              onChange={handleChange}
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Client Secret</span>
            <input
              type="text"
              name="clientSecret"
              value={form.clientSecret}
              onChange={handleChange}
              className={fieldClass}
              placeholder="Optional"
            />
            <span className="text-[11px] text-slate-500">Leave blank if your Cognito app client has no secret.</span>
          </label>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Username (email)</span>
            <input
              type="email"
              required
              name="username"
              value={form.username}
              onChange={handleChange}
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelClass}>Password</span>
            <input
              type="password"
              required
              name="password"
              value={form.password}
              onChange={handleChange}
              className={fieldClass}
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={auth.loading}
          className="rounded-full bg-emerald-600 px-6 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
        >
          {auth.loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <div className="mt-8">
        <h2 className="text-base font-semibold text-slate-900">Use an existing access token</h2>
        <p className="mt-1 text-xs text-slate-500">
          Paste a bearer token to skip the password grant and immediately talk to the API.
        </p>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row">
          <input
            type="text"
            name="existingToken"
            value={form.existingToken}
            onChange={handleChange}
            className={`${fieldClass} flex-1`}
            placeholder="eyJhbGciOi..."
          />
          <button
            type="button"
            onClick={handleUseToken}
            className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use token
          </button>
        </div>
      </div>
      {status ? <p className="mt-4 text-sm text-rose-600">{status}</p> : null}
      {auth.error ? <p className="mt-2 text-sm text-rose-600">{auth.error}</p> : null}
    </div>
  );
}
