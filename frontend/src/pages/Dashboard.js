import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import LanguageSwitcher from '../components/LanguageSwitcher';
import ThemeToggle from '../components/ThemeToggle';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Dashboard = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // If user data passed from auth callback, use it
    if (location.state?.user) {
      setUser(location.state.user);
      setLoading(false);
      return;
    }

    // Otherwise verify session
    const verifySession = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        navigate('/login');
        return;
      }

      try {
        const response = await axios.get(`${API}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        });
        setUser(response.data);
      } catch (error) {
        console.error('Session verification failed:', error);
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        navigate('/login');
      } finally {
        setLoading(false);
      }
    };

    verifySession();
  }, [location, navigate]);

  const handleLogout = async () => {
    try {
      await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      toast.success('Logged out successfully');
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
      navigate('/login');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background" data-testid="dashboard-page">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
              <span className="text-2xl text-primary-foreground">+</span>
            </div>
            <span className="text-xl font-semibold">{t('healthPortal')}</span>
          </div>
          <div className="flex items-center gap-4">
            <LanguageSwitcher />
            <ThemeToggle />
            <Button variant="outline" onClick={handleLogout} data-testid="logout-btn">
              {t('logout')}
            </Button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="text-start space-y-2">
            <h1 className="text-4xl font-semibold tracking-tight">
              {t('welcome')}, {user?.name}!
            </h1>
            <p className="text-lg text-muted-foreground">
              {t('userType')}: <span className="font-medium text-foreground">{user?.user_type}</span>
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-start">Profile Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-start">
                <div>
                  <p className="text-sm text-muted-foreground">Email</p>
                  <p className="font-medium">{user?.email}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">User Type</p>
                  <p className="font-medium">{user?.user_type}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Account ID</p>
                  <p className="font-mono text-sm">{user?.user_id}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-start">Quick Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button variant="outline" className="w-full justify-start" data-testid="view-profile-btn">
                  View Profile
                </Button>
                <Button variant="outline" className="w-full justify-start" data-testid="settings-btn">
                  Settings
                </Button>
                <Button variant="outline" className="w-full justify-start" data-testid="help-btn">
                  Help & Support
                </Button>
              </CardContent>
            </Card>
          </div>

          <Card className="bg-gradient-to-r from-primary/10 to-secondary/10 border-primary/20">
            <CardContent className="p-8 text-start">
              <h3 className="text-2xl font-semibold mb-2">{t('healthPortal')}</h3>
              <p className="text-muted-foreground">
                Your multilingual health platform is ready. This is a placeholder dashboard. More features coming soon!
              </p>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
