import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VerifyEmail = () => {
  const { token } = useParams();
  const { t } = useLanguage();
  const [status, setStatus] = useState('verifying'); // 'verifying' | 'success' | 'error'
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const verify = async () => {
      try {
        await axios.post(`${API}/auth/verify-email`, { token });
        setStatus('success');
      } catch (e) {
        setErrorMsg(e.response?.data?.detail || t('emailVerificationFailed'));
        setStatus('error');
      }
    };
    if (token) verify();
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-background">
      <Card className="w-full max-w-md">
        <CardContent className="pt-8 pb-8 text-center space-y-4">
          {status === 'verifying' && (
            <>
              <Loader2 className="w-12 h-12 text-primary animate-spin mx-auto" />
              <p className="text-lg font-medium">{t('verifyingEmail')}</p>
            </>
          )}
          {status === 'success' && (
            <>
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
              <p className="text-lg font-semibold">{t('emailVerified')}</p>
              <p className="text-sm text-muted-foreground">{t('emailVerifiedDesc')}</p>
              <Button asChild className="w-full mt-2">
                <Link to="/login?verified=1">{t('loginBtn')}</Link>
              </Button>
            </>
          )}
          {status === 'error' && (
            <>
              <XCircle className="w-12 h-12 text-destructive mx-auto" />
              <p className="text-lg font-semibold">{t('emailVerificationFailed')}</p>
              <p className="text-sm text-muted-foreground">{errorMsg}</p>
              <Button asChild variant="outline" className="w-full mt-2">
                <Link to="/login">{t('backToLogin')}</Link>
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default VerifyEmail;
