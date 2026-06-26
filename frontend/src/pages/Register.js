import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import LanguageSwitcher from '../components/LanguageSwitcher';
import ThemeToggle from '../components/ThemeToggle';
import {
  Mail, Lock, Eye, EyeOff, User as UserIcon, ArrowRight,
  Stethoscope, Pill, Wrench, Check,
} from 'lucide-react';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

/* ─── Google SVG ─────────────────────────────────────────────────── */
const GoogleIcon = () => (
  <svg className="w-4 h-4 me-2 shrink-0" viewBox="0 0 24 24">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
  </svg>
);

/* ─── Role selector ───────────────────────────────────────────────── */
const ROLES = [
  { id: 'Patient',             label: 'Patient',              icon: UserIcon,     desc: 'Book appointments & manage your health' },
  { id: 'Doctor',              label: 'Doctor',               icon: Stethoscope,  desc: 'Manage consultations & schedules' },
  { id: 'Pharmacy',            label: 'Pharmacy',             icon: Pill,         desc: 'Sell medicines & manage inventory' },
  { id: 'Biomedical Engineer', label: 'Biomedical Engineer',  icon: Wrench,       desc: 'Handle medical device service tickets' },
];

const RoleSelector = ({ value, onChange, t }) => (
  <div>
    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">{t('selectUserType')}</p>
    <div className="grid grid-cols-2 gap-2">
      {ROLES.map(({ id, label, icon: Icon, desc }) => {
        const sel = value === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            data-testid={`user-type-${id.toLowerCase().replace(' ', '-')}`}
            className={`relative rounded-xl border p-3 text-left transition-all ${
              sel
                ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20 ring-1 ring-emerald-500/30'
                : 'border-border hover:border-emerald-300 dark:hover:border-emerald-700'
            }`}
          >
            {sel && (
              <span className="absolute top-2 right-2 w-4 h-4 bg-emerald-500 rounded-full flex items-center justify-center">
                <Check className="w-2.5 h-2.5 text-white" />
              </span>
            )}
            <Icon className={`w-5 h-5 mb-1.5 ${sel ? 'text-emerald-600' : 'text-muted-foreground'}`} />
            <p className={`text-xs font-semibold ${sel ? 'text-emerald-700 dark:text-emerald-300' : ''}`}>{label}</p>
            <p className="text-[10px] text-muted-foreground leading-tight mt-0.5 hidden sm:block">{desc}</p>
          </button>
        );
      })}
    </div>
  </div>
);

/* ─── Left panel ─────────────────────────────────────────────────── */
const HeroPanel = () => (
  <div
    className="hidden lg:flex lg:flex-col relative overflow-hidden text-white"
    style={{ flex: '0 0 42%', background: 'linear-gradient(145deg, #022c22 0%, #0f172a 50%, #064e3b 100%)' }}
  >
    <div className="pointer-events-none absolute -top-24 -right-24 w-80 h-80 rounded-full bg-emerald-500/20 blur-3xl" />
    <div className="pointer-events-none absolute bottom-0 left-0 w-72 h-72 rounded-full bg-teal-500/10 blur-3xl" />
    <div className="pointer-events-none absolute inset-0 opacity-[0.06]"
         style={{ backgroundImage: 'radial-gradient(circle, #34d399 1px, transparent 1px)', backgroundSize: '28px 28px' }} />

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

      {/* Headline */}
      <div className="mb-10">
        <h2 className="text-3xl font-bold leading-tight mb-3">
          Join thousands of<br />
          <span className="text-emerald-400">Afghan healthcare</span><br />
          professionals.
        </h2>
        <p className="text-slate-400 text-sm leading-relaxed max-w-xs">
          Whether you're a patient, doctor, pharmacist or engineer — Faizan gives you the tools to deliver and receive care.
        </p>
      </div>

      {/* Step list */}
      <div className="space-y-5 mb-auto">
        {[
          { step: '01', title: 'Create your account', desc: 'Choose your role and register in 30 seconds.' },
          { step: '02', title: 'Complete your profile', desc: 'Add your specialty, location and working hours.' },
          { step: '03', title: 'Start using Faizan', desc: 'Book appointments, chat with AI, manage orders.' },
        ].map(({ step, title, desc }) => (
          <div key={step} className="flex items-start gap-4">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center shrink-0">
              <span className="text-xs font-bold text-emerald-400">{step}</span>
            </div>
            <div>
              <p className="text-sm font-semibold text-white">{title}</p>
              <p className="text-xs text-slate-400 mt-0.5">{desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom quote */}
      <div className="mt-10 border-t border-white/10 pt-8">
        <p className="text-xs text-slate-400 italic leading-relaxed">
          "Designed for Afghanistan — multilingual, encrypted, and built for the realities of Afghan healthcare."
        </p>
      </div>
    </div>
  </div>
);

/* ─── Register page ──────────────────────────────────────────────── */
const Register = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [name,     setName]     = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [userType, setUserType] = useState('Patient');
  const [showPw,   setShowPw]   = useState(false);
  const [loading,  setLoading]  = useState(false);

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await axios.post(`${API}/auth/register`, { name, email, password, user_type: userType });
      localStorage.setItem('token', res.data.token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      toast.success('Account created! Check your email to verify.');
      navigate('/dashboard', { state: { user: res.data.user } });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen flex bg-background" data-testid="register-page">
      <HeroPanel />

      {/* Form side */}
      <div className="flex-1 flex flex-col overflow-y-auto">

        {/* Top bar */}
        <div className="flex items-center justify-between px-8 pt-6 shrink-0">
          <div className="flex items-center gap-2 lg:hidden">
            <div className="w-8 h-8 rounded-xl bg-emerald-600 flex items-center justify-center">
              <span className="text-base font-bold text-white leading-none">+</span>
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
        <div className="flex-1 flex items-center justify-center px-8 py-10">
          <div className="w-full max-w-sm">

            {/* Heading */}
            <div className="mb-7">
              <h1 className="text-3xl font-bold tracking-tight mb-1">{t('createAccount')}</h1>
              <p className="text-sm text-muted-foreground">{t('subtitle')}</p>
            </div>

            <form onSubmit={handleRegister} className="space-y-4">

              {/* Role selector */}
              <RoleSelector value={userType} onChange={setUserType} t={t} />

              {/* Name */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t('name')}</label>
                <div className="relative">
                  <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    required
                    className="pl-9 h-11 rounded-xl"
                    placeholder="Ahmad Shah"
                    data-testid="register-name-input"
                  />
                </div>
              </div>

              {/* Email */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t('email')}</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    required
                    className="pl-9 h-11 rounded-xl"
                    placeholder="you@example.com"
                    data-testid="register-email-input"
                  />
                </div>
              </div>

              {/* Password */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t('password')}</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    type={showPw ? 'text' : 'password'}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    className="pl-9 pr-10 h-11 rounded-xl"
                    placeholder="Min. 8 characters"
                    data-testid="register-password-input"
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
                className="w-full h-11 rounded-xl font-semibold text-sm mt-1 bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-600/20 transition-all"
                disabled={loading}
                data-testid="register-submit-btn"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 100 16v-4l-3 3 3 3v-4a8 8 0 01-8-8z" />
                    </svg>
                    Creating account…
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    {t('registerBtn')} <ArrowRight className="w-4 h-4" />
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
              data-testid="google-register-btn"
            >
              <GoogleIcon />
              {t('googleLogin')}
            </Button>

            {/* Link to login */}
            <p className="text-center text-sm text-muted-foreground mt-6">
              {t('alreadyHaveAccount')}{' '}
              <Link
                to="/login"
                className="text-emerald-600 font-semibold hover:underline"
                data-testid="login-link"
              >
                {t('signInHere')}
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Register;
