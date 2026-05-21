import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import LanguageSwitcher from '../components/LanguageSwitcher';
import ThemeToggle from '../components/ThemeToggle';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Login = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await axios.post(`${API}/auth/login`, { email, password });
      localStorage.setItem('token', response.data.token);
      localStorage.setItem('user', JSON.stringify(response.data.user));
      toast.success(t('welcomeBack'));
      navigate('/dashboard', { state: { user: response.data.user } });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left Side - Form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-lg">
          {/* Header */}
          <div className="flex items-center justify-between mb-12">
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
                <span className="text-2xl text-primary-foreground">+</span>
              </div>
              <span className="text-xl font-semibold">{t('healthPortal')}</span>
            </div>
            <div className="flex items-center gap-3">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
          </div>

          {/* Form */}
          <div className="space-y-6">
            <div className="space-y-2 text-start">
              <h1 className="text-4xl font-semibold tracking-tight">{t('welcomeBack')}</h1>
              <p className="text-base text-muted-foreground leading-relaxed">{t('subtitle')}</p>
            </div>

            <form onSubmit={handleLogin} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="email" className="text-start block">
                  {t('email')}
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  data-testid="login-email-input"
                  className="rounded-md"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password" className="text-start block">
                  {t('password')}
                </Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  data-testid="login-password-input"
                  className="rounded-md"
                />
              </div>

              <Button
                type="submit"
                className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-medium"
                disabled={loading}
                data-testid="login-submit-btn"
              >
                {loading ? '...' : t('loginBtn')}
              </Button>
            </form>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-4 text-muted-foreground">{t('orContinueWith')}</span>
              </div>
            </div>

            <Button
              variant="outline"
              className="w-full font-medium"
              onClick={handleGoogleLogin}
              data-testid="google-login-btn"
            >
              <svg className="w-5 h-5 me-2" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              {t('googleLogin')}
            </Button>

            <p className="text-center text-sm text-muted-foreground">
              {t('dontHaveAccount')}{' '}
              <Link to="/register" className="text-primary font-medium hover:underline" data-testid="register-link">
                {t('signUpHere')}
              </Link>
            </p>
          </div>
        </div>
      </div>

      {/* Right Side - Image */}
      <div
        className="hidden lg:flex flex-1 bg-cover bg-center relative"
        style={{
          backgroundImage:
            'url(https://static.prod-images.emergentagent.com/jobs/1289d8f2-99a7-4af7-a216-024d8287163f/images/8ca33d648d88e97b8541f7178182ce65f197230da84d828a031e8795e8b1a640.png)',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent" />
      </div>
    </div>
  );
};

export default Login;
