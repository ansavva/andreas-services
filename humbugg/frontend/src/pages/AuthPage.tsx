import { Button, Input } from '@ansavva/design-system';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';

import { Card, Shell, StatusMessage } from '../components/Layout';
import { useAuth } from '../context/AuthContext';
import { validatePassword } from '../utils/validation';

type Mode = 'login' | 'signup' | 'confirm' | 'forgot';

export default function AuthPage({ mode }: { mode: Mode }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(() => typeof window === 'undefined' ? '' : sessionStorage.getItem('humbugg:email') ?? '');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [stage, setStage] = useState<'request' | 'confirm'>('request');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const title = mode === 'login' ? 'Welcome back' : mode === 'signup' ? 'Create your Humbugg account' : mode === 'confirm' ? 'Check your email' : 'Reset your password';

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage(null);
    try {
      if (mode === 'login') {
        await auth.login(email.trim(), password);
        navigate(sessionStorage.getItem('humbugg:returnTo') ?? '/app');
      } else if (mode === 'signup') {
        const passwordError = validatePassword(password); if (passwordError) { setMessage(passwordError); return; }
        const normalizedEmail = email.trim(); await auth.register(normalizedEmail, password); sessionStorage.setItem('humbugg:email', normalizedEmail); navigate('/confirm');
      } else if (mode === 'confirm') {
        await auth.confirm(email.trim(), code.trim()); setMessage('Your email is confirmed. You can sign in now.');
      } else if (stage === 'request') {
        const normalizedEmail = email.trim(); await auth.beginReset(normalizedEmail); sessionStorage.setItem('humbugg:email', normalizedEmail); setStage('confirm'); setMessage('We sent a reset code to your email.');
      } else {
        const passwordError = validatePassword(password); if (passwordError) { setMessage(passwordError); return; }
        await auth.finishReset(email.trim(), code.trim(), password); setMessage('Password updated. You can sign in now.');
      }
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Something went wrong.'); }
    finally { setBusy(false); }
  }

  const needsCode = mode === 'confirm' || (mode === 'forgot' && stage === 'confirm');
  const needsPassword = mode === 'login' || mode === 'signup' || (mode === 'forgot' && stage === 'confirm');
  return (
    <Shell>
      <div className="mx-auto grid max-w-5xl gap-10 py-8 lg:grid-cols-[.85fr_1.15fr] lg:items-center">
        <div className="hidden lg:block"><p className="eyebrow">A calmer way to coordinate</p><h1 className="mt-4 font-heading text-5xl font-semibold leading-tight">The magic stays secret.<br />The planning stays simple.</h1><p className="mt-5 max-w-md leading-7 text-muted">One account keeps your groups, wish lists, and private assignments together.</p></div>
        <Card className="mx-auto w-full max-w-xl p-8 sm:p-10">
          <h1 className="font-heading text-3xl font-semibold">{title}</h1>
          <p className="mt-2 text-muted">{mode === 'confirm' ? 'Enter the six-digit confirmation code we sent you.' : 'Use your email address to continue.'}</p>
          <form className="mt-7 space-y-5" onSubmit={submit}>
            <label className="field-label">Email address<Input type="email" autoComplete="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            {needsCode && <label className="field-label">Confirmation code<Input inputMode="numeric" autoComplete="one-time-code" required minLength={6} maxLength={6} pattern="[0-9]{6}" title="Enter the six-digit code from your email." value={code} onChange={(e) => setCode(e.target.value)} /></label>}
            {needsPassword && <label className="field-label">{mode === 'forgot' ? 'New password' : 'Password'}<Input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={8} maxLength={256} pattern={mode === 'login' ? undefined : '(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9]).{8,}'} title={mode === 'login' ? undefined : 'Use at least 8 characters with uppercase, lowercase, and a number.'} required value={password} onChange={(e) => setPassword(e.target.value)} />{mode !== 'login' && <span className="font-normal text-muted">At least 8 characters with uppercase, lowercase, and a number.</span>}</label>}
            <StatusMessage message={message} tone={message?.includes('confirmed') || message?.includes('updated') || message?.includes('sent') ? 'success' : 'error'} />
            <Button type="submit" className="w-full" size="lg" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : mode === 'signup' ? 'Create account' : mode === 'confirm' ? 'Confirm email' : stage === 'request' ? 'Send reset code' : 'Update password'}</Button>
          </form>
          <div className="mt-6 flex flex-wrap justify-between gap-3 text-sm">
            {mode !== 'login' ? <Link className="text-accent hover:underline" to="/login">Back to sign in</Link> : <><Link className="text-accent hover:underline" to="/signup">Create an account</Link><Link className="text-accent hover:underline" to="/forgot-password">Forgot password?</Link></>}
          </div>
        </Card>
      </div>
    </Shell>
  );
}
