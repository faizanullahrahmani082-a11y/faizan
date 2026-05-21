import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import LanguageSwitcher from '../components/LanguageSwitcher';
import ThemeToggle from '../components/ThemeToggle';
import AppointmentsTab from '../components/AppointmentsTab';
import MedicinesTab from '../components/MedicinesTab';
import AIChatTab from '../components/AIChatTab';
import MapTab from '../components/MapTab';
import SubscriptionTab from '../components/SubscriptionTab';
import ScheduleTab from '../components/ScheduleTab';
import OrdersTab from '../components/OrdersTab';
import ReportsTab from '../components/ReportsTab';
import NotificationBell from '../components/NotificationBell';
import ProfilePictureUpload from '../components/ProfilePictureUpload';
import { Calendar, Pill, Bot, MapPin, Crown, LayoutDashboard, BadgeCheck, Star, CalendarDays, ShoppingCart, FileText } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const Dashboard = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (location.state?.user) {
      setUser(location.state.user);
      setLoading(false);
      return;
    }

    const verifySession = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        navigate('/login');
        return;
      }
      try {
        const response = await api.get('/auth/me');
        setUser(response.data);
      } catch (error) {
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
      await api.post('/auth/logout');
    } catch (e) {
      console.error('Logout error:', e);
    }
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    toast.success('Logged out');
    navigate('/login');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  const userType = user?.user_type;
  const canSubscribe = ['Pharmacy', 'Doctor', 'Biomedical Engineer'].includes(userType);

  // Determine which tabs to show based on role
  const showAppointments = ['Patient', 'Doctor'].includes(userType);
  const showMedicines = true;
  const showMap = true;
  const showAI = true;
  const showSchedule = userType === 'Doctor';
  const showOrders = ['Patient', 'Pharmacy'].includes(userType);
  const showReports = ['Doctor', 'Pharmacy', 'Biomedical Engineer'].includes(userType);

  const handleProfilePictureUpdate = (newUrl) => {
    setUser({ ...user, picture: newUrl });
    const stored = JSON.parse(localStorage.getItem('user') || '{}');
    localStorage.setItem('user', JSON.stringify({ ...stored, picture: newUrl }));
  };

  return (
    <div className="min-h-screen bg-background" data-testid="dashboard-page">
      <header className="border-b bg-card sticky top-0 z-10">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
              <span className="text-2xl text-primary-foreground">+</span>
            </div>
            <span className="text-xl font-semibold hidden sm:inline">{t('healthPortal')}</span>
          </div>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <LanguageSwitcher />
            <ThemeToggle />
            <Button variant="outline" onClick={handleLogout} data-testid="logout-btn">
              {t('logout')}
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6">
        <div className="mb-6 flex items-start gap-4 flex-wrap">
          <ProfilePictureUpload user={user} onUpdate={handleProfilePictureUpdate} />
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-3xl font-semibold tracking-tight text-start">
                {t('welcome')}, {user?.name}
              </h1>
              {user?.is_verified && <Badge className="bg-primary"><BadgeCheck className="w-3 h-3 me-1" />{t('verified')}</Badge>}
              {user?.is_featured && <Badge className="bg-yellow-500 text-white"><Star className="w-3 h-3 me-1" />{t('featured')}</Badge>}
            </div>
            <p className="text-muted-foreground text-start">
              {t('userType')}: <span className="font-medium text-foreground">{user?.user_type}</span>
            </p>
          </div>
        </div>

        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="w-full flex-wrap h-auto justify-start gap-1">
            <TabsTrigger value="overview" data-testid="tab-overview">
              <LayoutDashboard className="w-4 h-4 me-1" /> {t('overview')}
            </TabsTrigger>
            {showAppointments && (
              <TabsTrigger value="appointments" data-testid="tab-appointments">
                <Calendar className="w-4 h-4 me-1" /> {t('appointments')}
              </TabsTrigger>
            )}
            {showSchedule && (
              <TabsTrigger value="schedule" data-testid="tab-schedule">
                <CalendarDays className="w-4 h-4 me-1" /> {t('schedule')}
              </TabsTrigger>
            )}
            {showMedicines && (
              <TabsTrigger value="medicines" data-testid="tab-medicines">
                <Pill className="w-4 h-4 me-1" /> {t('medicines')}
              </TabsTrigger>
            )}
            {showOrders && (
              <TabsTrigger value="orders" data-testid="tab-orders">
                <ShoppingCart className="w-4 h-4 me-1" /> {t('orders')}
              </TabsTrigger>
            )}
            {showAI && (
              <TabsTrigger value="ai" data-testid="tab-ai">
                <Bot className="w-4 h-4 me-1" /> {t('aiAssistant')}
              </TabsTrigger>
            )}
            {showMap && (
              <TabsTrigger value="map" data-testid="tab-map">
                <MapPin className="w-4 h-4 me-1" /> {t('map')}
              </TabsTrigger>
            )}
            {canSubscribe && (
              <TabsTrigger value="subscription" data-testid="tab-subscription">
                <Crown className="w-4 h-4 me-1" /> {t('subscription')}
              </TabsTrigger>
            )}
            {showReports && (
              <TabsTrigger value="reports" data-testid="tab-reports">
                <FileText className="w-4 h-4 me-1" /> {t('reports')}
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardHeader><CardTitle className="text-start text-base">Profile</CardTitle></CardHeader>
                <CardContent className="text-start space-y-1 text-sm">
                  <div><span className="text-muted-foreground">Email:</span> {user?.email}</div>
                  <div><span className="text-muted-foreground">Type:</span> {user?.user_type}</div>
                  {user?.phone && <div><span className="text-muted-foreground">Phone:</span> {user.phone}</div>}
                </CardContent>
              </Card>

              {showAppointments && (
                <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => document.querySelector('[data-testid="tab-appointments"]').click()}>
                  <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><Calendar className="w-4 h-4" /> {t('appointments')}</CardTitle></CardHeader>
                  <CardContent className="text-start text-sm text-muted-foreground">
                    Manage your medical appointments with calendar integration.
                  </CardContent>
                </Card>
              )}

              <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => document.querySelector('[data-testid="tab-ai"]').click()}>
                <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><Bot className="w-4 h-4" /> {t('aiAssistant')}</CardTitle></CardHeader>
                <CardContent className="text-start text-sm text-muted-foreground">
                  AI symptom checker & device fault helper powered by Gemini.
                </CardContent>
              </Card>

              <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => document.querySelector('[data-testid="tab-medicines"]').click()}>
                <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><Pill className="w-4 h-4" /> {t('medicines')}</CardTitle></CardHeader>
                <CardContent className="text-start text-sm text-muted-foreground">
                  {userType === 'Pharmacy' ? 'Manage your medicine catalog.' : 'Search medicines from nearby pharmacies.'}
                </CardContent>
              </Card>

              <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => document.querySelector('[data-testid="tab-map"]').click()}>
                <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><MapPin className="w-4 h-4" /> {t('map')}</CardTitle></CardHeader>
                <CardContent className="text-start text-sm text-muted-foreground">
                  Find 24/7 pharmacies on the map.
                </CardContent>
              </Card>

              {canSubscribe && (
                <Card className="cursor-pointer hover:shadow-md transition-shadow border-primary/30 bg-gradient-to-br from-primary/5 to-secondary/5" onClick={() => document.querySelector('[data-testid="tab-subscription"]').click()}>
                  <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><Crown className="w-4 h-4 text-primary" /> {t('subscription')}</CardTitle></CardHeader>
                  <CardContent className="text-start text-sm text-muted-foreground">
                    Get verified badge & featured listing.
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          {showAppointments && (
            <TabsContent value="appointments"><AppointmentsTab user={user} /></TabsContent>
          )}
          {showSchedule && (
            <TabsContent value="schedule"><ScheduleTab /></TabsContent>
          )}
          {showMedicines && (
            <TabsContent value="medicines"><MedicinesTab user={user} /></TabsContent>
          )}
          {showOrders && (
            <TabsContent value="orders"><OrdersTab user={user} /></TabsContent>
          )}
          {showAI && (
            <TabsContent value="ai"><AIChatTab user={user} /></TabsContent>
          )}
          {showMap && (
            <TabsContent value="map"><MapTab /></TabsContent>
          )}
          {canSubscribe && (
            <TabsContent value="subscription"><SubscriptionTab user={user} /></TabsContent>
          )}
          {showReports && (
            <TabsContent value="reports"><ReportsTab user={user} /></TabsContent>
          )}
        </Tabs>
      </main>
    </div>
  );
};

export default Dashboard;
