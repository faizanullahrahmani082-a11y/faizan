import React, { useState } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import LanguageSwitcher from '../components/LanguageSwitcher';
import ThemeToggle from '../components/ThemeToggle';
import { Mail, Lock, Eye, EyeOff, ArrowRight, CheckCircle2, Stethoscope, Bot, Pill, Globe, ShieldCheck } from 'lucide-react';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000';
const API = `${BACKEND_URL}/api`;

const FEATURES = [
  { icon: Stethoscope, text: '500+ verified doctors across Afghanistan' },
  { icon: Bot,         text: 'AI symptom checker powered by Gemini' },
  { icon: Pill,        text: 'Pharmacies open 24/7 near you' },
  { icon: Globe,       text: 'Available in Dari, Pashto & English' },
  { icon: ShieldCheck, text: 'AES-256 encrypted medical records' },
];

const STATS = [
  { value: '500+', label: 'Doctors' },
  { value: '24/7', label: 'Pharmacies' },
  { value: '3',    label: 'Languages' },
];

/* ─── Google SVG ─────────────────────────────────────────────────── */
const GoogleIcon = () => (
  <svg className="w-4 h-4 me-2 shrink-0" viewBox="0 0 24 24">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
  </svg>
);

/* ─── Left decorative panel ──────────────────────────────────────── */
const HeroPanel = () => (
  <div className="hidden lg:flex lg:flex-col relative overflow-hidden bg-gradient-to-br from-slate-950 via-emerald-950 to-slate-900 text-white"
       style={{ flex: '0 0 46%' }}>

    {/* Animated glow orbs */}
    <div className="pointer-events-none absolute -top-32 -left-32 w-96 h-96 rounded-full bg-emerald-500/20 blur-3xl" />
    <div className="pointer-events-none absolute top-1/2 -right-24 w-72 h-72 rounded-full bg-teal-400/15 blur-3xl" />
    <div className="pointer-events-none absolute -bottom-24 left-1/3 w-64 h-64 rounded-full bg-emerald-600/20 blur-3xl" />

    {/* Subtle dot grid */}
    <div className="pointer-events-none absolute inset-0 opacity-[0.07]"
         style={{
           backgroundImage: 'radial-gradient(circle, #34d399 1px, transparent 1px)',
           backgroundSize: '28px 28px',
         }} />

    {/* Content */}
    <div className="relative z-10 flex flex-col h-full p-12">

      {/* Logo */}
      <div className="flex items-center gap-3 mb-16">
        <div className="w-11 h-11 rounded-2xl bg-emerald-500 flex items-center justify-center shadow-lg shadow-emerald-500/30">
          <span className="text-2xl font-bold text-white leading-none">+</span>
        </div>
        <div>
          <p className="text-lg font-bold tracking-tight leading-none">Faizan</p>
          <p className="text-xs text-emerald-400 mt-0.5 leading-none">Afghan Health Portal</p>
        </div>
      </div>

      {/* Hero text */}
      <div className="mb-10">
        <h2 className="text-3xl font-bold leading-tight mb-3">
          Healthcare for<br />
          <span className="text-emerald-400">every Afghan.</span>
        </h2>
        <p className="text-slate-400 text-sm leading-relaxed max-w-xs">
          Connect with verified doctors, order medicines, and manage your health records — securely, in your language.
        </p>
      </div>

      {/* Features */}
      <ul className="space-y-3 mb-auto">
        {FEATURES.map(({ icon: Icon, text }) => (
          <li key={text} className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg bg-emerald-500/15 border border-emerald-500/20 flex items-center justify-center shrink-0 mt-0.5">
              <Icon className="w-3.5 h-3.5 text-emerald-400" />
            </div>
            <span className="text-sm text-slate-300 leading-snug">{text}</span>
          </li>
        ))}
      </ul>

      {/* Stats */}
      <div className="mt-10 grid grid-cols-3 gap-4 border-t border-white/10 pt-8">
        {STATS.map(({ value, label }) => (
          <div key={label}>
            <p className="text-2xl font-bold text-white">{value}</p>
            <p className="text-xs text-slate-400 mt-0.5">{label}</p>
          </div>
        ))}
      </div>
    </div>
  </div>
);

/* ─── Login page ─────────────────────────────────────────────────── */
const Login = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const emailVerified = searchParams.get('verified') === '1';

  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]     = useState(false);
  const [loading, setLoading]   = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await axios.post(`${API}/auth/login`, { email, password });
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      toast.success(t('welcomeBack'));
      navigate('/dashboard', { state: { user: res.data.user } });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen flex bg-background" data-testid="login-page">
      <HeroPanel />

      {/* Form side */}
      <div className="flex-1 flex flex-col">

        {/* Top bar */}
        <div className="flex items-center justify-between px-8 pt-6">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 lg:hidden">
            <div className="w-8 h-8 rounded-xl bg-primary flex items-center justify-center">
              <span className="text-base font-bold text-primary-foreground leading-none">+</span>
            </div>
            <span className="font-semibold text-sm">{t('healthPortal')}</span>
          </div>
          <div className="hidden lg:block" />
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
        </div>

        {/* Form container */}
        <div className="flex-1 flex items-center justify-center px-8 py-12">
          <div className="w-full max-w-sm">

            {/* Email verified banner */}
            {emailVerified && (
              <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-800 px-4 py-3 mb-6">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <p className="text-sm text-emerald-800 dark:text-emerald-300 font-medium">{t('emailVerified')}</p>
              </div>
            )}

            {/* Heading */}
            <div className="mb-8">
              <h1 className="text-3xl font-bold tracking-tight mb-1">{t('welcomeBack')}</h1>
              <p className="text-sm text-muted-foreground">{t('subtitle')}</p>
            </div>

            {/* Form */}
            <form onSubmit={handleLogin} className="space-y-4">

              {/* Email */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t('email')}</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    required
                    className="pl-9 h-11 rounded-xl"
                    placeholder="you@example.com"
                    data-testid="login-email-input"
                  />
                </div>
              </div>

              {/* Password */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">{t('password')}</label>
                  <Link
                    to="/forgot-password"
                    className="text-xs text-primary hover:underline"
                    data-testid="forgot-password-link"
                  >
                    {t('forgotPassword')}
                  </Link>
                </div>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    id="password"
                    type={showPw ? 'text' : 'password'}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    className="pl-9 pr-10 h-11 rounded-xl"
                    placeholder="••••••••"
                    data-testid="login-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(v => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    tabIndex={-1}
                  >
                    {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Submit */}
              <Button
                type="submit"
                className="w-full h-11 rounded-xl font-semibold text-sm mt-2 bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-600/20 transition-all"
                disabled={loading}
                data-testid="login-submit-btn"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Signing in…
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    {t('loginBtn')} <ArrowRight className="w-4 h-4" />
                  </span>
                )}
              </Button>
            </form>

            {/* Divider */}
            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-background px-3 text-xs text-muted-foreground uppercase tracking-wider">
                  {t('orContinueWith')}
                </span>
              </div>
            </div>

            {/* Google */}
            <Button
              variant="outline"
              className="w-full h-11 rounded-xl font-medium text-sm"
              onClick={handleGoogleLogin}
              data-testid="google-login-btn"
            >
              <GoogleIcon />
              {t('googleLogin')}
            </Button>

            {/* Links */}
            <p className="text-center text-sm text-muted-foreground mt-6">
              {t('dontHaveAccount')}{' '}
              <Link
                to="/register"
                className="text-emerald-600 font-semibold hover:underline"
                data-testid="register-link"
              >
                {t('signUpHere')}
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
