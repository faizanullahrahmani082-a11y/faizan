import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../components/ui/sheet';
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
import ProfileTab from '../components/ProfileTab';
import ServiceTicketsTab from '../components/ServiceTicketsTab';
import ReviewsTab from '../components/ReviewsTab';
import MedicalRecordTab from '../components/MedicalRecordTab';
import NotificationBell from '../components/NotificationBell';
import ProfilePictureUpload from '../components/ProfilePictureUpload';
import {
  Calendar, Pill, Bot, MapPin, Crown, LayoutDashboard, BadgeCheck,
  Star, CalendarDays, ShoppingCart, FileText, UserCircle, Wrench,
  Shield, Navigation, HeartPulse, Menu, LogOut, ChevronLeft, ChevronRight,
} from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const Dashboard = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [liveStats, setLiveStats] = useState({});
  const [geoLoading, setGeoLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (location.state?.user) {
      setUser(location.state.user);
      setLoading(false);
      return;
    }
    const verifySession = async () => {
      const token = localStorage.getItem('token');
      if (!token) { navigate('/login'); return; }
      try {
        const response = await api.get('/auth/me');
        setUser(response.data);
      } catch {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        navigate('/login');
      } finally {
        setLoading(false);
      }
    };
    verifySession();
  }, [location, navigate]);

  useEffect(() => { if (user) loadLiveStats(user); }, [user]);

  const handleLogout = async () => {
    try { await api.post('/auth/logout'); } catch (e) { console.error(e); }
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    toast.success('Logged out');
    navigate('/login');
  };

  const loadLiveStats = async (u) => {
    if (!u) return;
    const stats = {};
    try {
      const apptRes = await api.get('/appointments/me');
      const appts = apptRes.data.appointments || [];
      stats.upcoming = appts.filter(a => ['pending', 'confirmed'].includes(a.status)).length;
    } catch { /* ignore */ }
    try {
      const ordersRes = await api.get('/orders/me');
      const orders = ordersRes.data.orders || [];
      stats.pendingOrders = orders.filter(o => o.status === 'pending').length;
    } catch { /* ignore */ }
    try {
      const reviewRes = await api.get(`/reviews/user/${u.user_id}`);
      stats.avgRating = reviewRes.data.average_rating;
      stats.totalReviews = reviewRes.data.total_reviews;
    } catch { /* ignore */ }
    if (['Doctor', 'Pharmacy', 'Biomedical Engineer'].includes(u.user_type)) {
      try {
        const reportRes = await api.get('/reports/monthly');
        stats.gmv = reportRes.data.gmv;
      } catch { /* ignore */ }
    }
    setLiveStats(stats);
  };

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) { toast.error('Geolocation not supported'); return; }
    setGeoLoading(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          await api.post('/location', { latitude: pos.coords.latitude, longitude: pos.coords.longitude });
          toast.success(t('locationUpdated'));
        } catch { toast.error(t('error')); }
        finally { setGeoLoading(false); }
      },
      () => { toast.error(t('locationDenied')); setGeoLoading(false); }
    );
  };

  const handleProfilePictureUpdate = (newUrl) => {
    setUser({ ...user, picture: newUrl });
    const stored = JSON.parse(localStorage.getItem('user') || '{}');
    localStorage.setItem('user', JSON.stringify({ ...stored, picture: newUrl }));
  };

  const handleProfileUpdate = (updatedUser) => {
    setUser(updatedUser);
    localStorage.setItem('user', JSON.stringify(updatedUser));
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
      </div>
    );
  }

  const userType = user?.user_type;
  const canSubscribe = ['Pharmacy', 'Doctor', 'Biomedical Engineer'].includes(userType);
  const showAppointments = ['Patient', 'Doctor'].includes(userType);
  const showSchedule = userType === 'Doctor';
  const showOrders = ['Patient', 'Pharmacy'].includes(userType);
  const showReports = ['Doctor', 'Pharmacy', 'Biomedical Engineer'].includes(userType);
  const showMedicalRecord = userType === 'Patient';

  const navItems = [
    { id: 'overview',       icon: LayoutDashboard, label: t('overview'),        show: true },
    { id: 'appointments',   icon: Calendar,         label: t('appointments'),    show: showAppointments },
    { id: 'schedule',       icon: CalendarDays,     label: t('schedule'),        show: showSchedule },
    { id: 'medicines',      icon: Pill,             label: t('medicines'),       show: true },
    { id: 'orders',         icon: ShoppingCart,     label: t('orders'),          show: showOrders },
    { id: 'ai',             icon: Bot,              label: t('aiAssistant'),     show: true },
    { id: 'map',            icon: MapPin,           label: t('map'),             show: true },
    { id: 'medical-record', icon: HeartPulse,       label: t('medicalRecord'),   show: showMedicalRecord },
    { id: 'subscription',   icon: Crown,            label: t('subscription'),    show: canSubscribe },
    { id: 'reports',        icon: FileText,         label: t('reports'),         show: showReports },
    { id: 'tickets',        icon: Wrench,           label: t('serviceTickets'),  show: true },
    { id: 'reviews',        icon: Star,             label: t('reviews'),         show: true },
    { id: 'profile',        icon: UserCircle,       label: t('myProfile'),       show: true },
  ].filter(i => i.show);

  const NavList = ({ onSelect }) => (
    <nav className="flex flex-col gap-0.5 px-2 py-3 flex-1">
      {navItems.map(({ id, icon: Icon, label }) => {
        const active = activeTab === id;
        return (
          <button
            key={id}
            onClick={() => { setActiveTab(id); onSelect?.(); }}
            data-testid={`tab-${id}`}
            className={`
              flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all w-full text-left
              ${active
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent'
              }
            `}
          >
            <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-primary-foreground' : ''}`} />
            {!collapsed && <span className="truncate">{label}</span>}
          </button>
        );
      })}
    </nav>
  );

  const renderContent = () => {
    switch (activeTab) {
      case 'overview':       return <OverviewContent />;
      case 'appointments':   return showAppointments   ? <AppointmentsTab user={user} />              : null;
      case 'schedule':       return showSchedule       ? <ScheduleTab />                              : null;
      case 'medicines':      return                      <MedicinesTab user={user} />;
      case 'orders':         return showOrders         ? <OrdersTab user={user} />                    : null;
      case 'ai':             return                      <AIChatTab user={user} />;
      case 'map':            return                      <MapTab />;
      case 'medical-record': return showMedicalRecord  ? <MedicalRecordTab user={user} />             : null;
      case 'subscription':   return canSubscribe       ? <SubscriptionTab user={user} />              : null;
      case 'reports':        return showReports        ? <ReportsTab user={user} />                   : null;
      case 'tickets':        return                      <ServiceTicketsTab user={user} />;
      case 'reviews':        return                      <ReviewsTab user={user} />;
      case 'profile':        return                      <ProfileTab user={user} onUpdate={handleProfileUpdate} />;
      default:               return null;
    }
  };

  const OverviewContent = () => (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {showAppointments && (
          <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('appointments')}>
            <CardContent className="p-4 text-start">
              <Calendar className="w-5 h-5 text-primary mb-1" />
              <p className="text-2xl font-bold">{liveStats.upcoming ?? '–'}</p>
              <p className="text-xs text-muted-foreground">{t('upcomingAppointments')}</p>
            </CardContent>
          </Card>
        )}
        {showOrders && (
          <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('orders')}>
            <CardContent className="p-4 text-start">
              <ShoppingCart className="w-5 h-5 text-secondary mb-1" />
              <p className="text-2xl font-bold">{liveStats.pendingOrders ?? '–'}</p>
              <p className="text-xs text-muted-foreground">{t('pendingOrders')}</p>
            </CardContent>
          </Card>
        )}
        {liveStats.totalReviews > 0 && (
          <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('reviews')}>
            <CardContent className="p-4 text-start">
              <Star className="w-5 h-5 text-yellow-500 mb-1" />
              <p className="text-2xl font-bold">{liveStats.avgRating?.toFixed(1) ?? '–'}</p>
              <p className="text-xs text-muted-foreground">{t('myAvgRating')} ({liveStats.totalReviews})</p>
            </CardContent>
          </Card>
        )}
        {liveStats.gmv != null && (
          <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('reports')}>
            <CardContent className="p-4 text-start">
              <FileText className="w-5 h-5 text-emerald-500 mb-1" />
              <p className="text-2xl font-bold">${liveStats.gmv?.toFixed(0) ?? '0'}</p>
              <p className="text-xs text-muted-foreground">{t('thisMonthGmv')}</p>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('profile')}>
          <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><UserCircle className="w-4 h-4" /> {t('myProfile')}</CardTitle></CardHeader>
          <CardContent className="text-start space-y-1 text-sm">
            <div><span className="text-muted-foreground">Email:</span> {user?.email}</div>
            {user?.phone && <div><span className="text-muted-foreground">{t('phone')}:</span> {user.phone}</div>}
            {user?.profile_data?.specialty && <div><span className="text-muted-foreground">{t('specialty')}:</span> <span className="font-medium text-primary">{user.profile_data.specialty}</span></div>}
            {user?.profile_data?.hospital && <div><span className="text-muted-foreground">{t('hospital')}:</span> {user.profile_data.hospital}</div>}
            <p className="text-xs text-primary mt-2 font-medium">{t('editProfile')} →</p>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('ai')}>
          <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><Bot className="w-4 h-4" /> {t('aiAssistant')}</CardTitle></CardHeader>
          <CardContent className="text-start text-sm text-muted-foreground">AI symptom checker & device fault helper powered by Gemini.</CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('medicines')}>
          <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><Pill className="w-4 h-4" /> {t('medicines')}</CardTitle></CardHeader>
          <CardContent className="text-start text-sm text-muted-foreground">
            {userType === 'Pharmacy' ? 'Manage your medicine catalog.' : 'Search medicines from nearby pharmacies.'}
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setActiveTab('map')}>
          <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><MapPin className="w-4 h-4" /> {t('map')}</CardTitle></CardHeader>
          <CardContent className="text-start text-sm text-muted-foreground">Find 24/7 pharmacies &amp; doctors on the map.</CardContent>
        </Card>
        {canSubscribe && (
          <Card className="cursor-pointer hover:shadow-md transition-shadow border-primary/30 bg-gradient-to-br from-primary/5 to-secondary/5" onClick={() => setActiveTab('subscription')}>
            <CardHeader><CardTitle className="text-start text-base flex items-center gap-2"><Crown className="w-4 h-4 text-primary" /> {t('subscription')}</CardTitle></CardHeader>
            <CardContent className="text-start text-sm text-muted-foreground">Get verified badge &amp; featured listing.</CardContent>
          </Card>
        )}
        <Card className="cursor-pointer hover:shadow-md transition-shadow border-dashed" onClick={handleUseMyLocation}>
          <CardContent className="p-4 flex items-center gap-3 text-start h-full">
            <Navigation className={`w-6 h-6 text-primary shrink-0 ${geoLoading ? 'animate-pulse' : ''}`} />
            <div>
              <p className="font-medium text-sm">{t('useMyLocation')}</p>
              <p className="text-xs text-muted-foreground">{geoLoading ? t('detectingLocation') : 'Share GPS with the platform'}</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex flex-col" data-testid="dashboard-page">
      {/* ── Header ── */}
      <header className="border-b bg-card sticky top-0 z-20">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* Hamburger – mobile only */}
            <button
              className="lg:hidden p-2 rounded-lg hover:bg-accent transition-colors"
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="w-9 h-9 bg-primary rounded-xl flex items-center justify-center shrink-0">
              <span className="text-xl font-bold text-primary-foreground leading-none">+</span>
            </div>
            <span className="text-lg font-semibold hidden sm:inline">{t('healthPortal')}</span>
          </div>

          <div className="flex items-center gap-2">
            {user?.is_admin && (
              <Button variant="outline" size="sm" onClick={() => navigate('/admin')} data-testid="admin-btn">
                <Shield className="w-4 h-4 me-1" /> Admin
              </Button>
            )}
            <Button variant="outline" size="icon" onClick={handleUseMyLocation} disabled={geoLoading} title={t('useMyLocation')} data-testid="geo-btn">
              <Navigation className={`w-4 h-4 ${geoLoading ? 'animate-pulse' : ''}`} />
            </Button>
            <NotificationBell />
            <LanguageSwitcher />
            <ThemeToggle />
            <Button variant="outline" size="sm" onClick={handleLogout} data-testid="logout-btn">
              <LogOut className="w-4 h-4 me-1" />
              <span className="hidden sm:inline">{t('logout')}</span>
            </Button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Desktop Sidebar ── */}
        <aside className={`
          hidden lg:flex flex-col border-r bg-card transition-all duration-200 shrink-0 sticky top-[57px] h-[calc(100vh-57px)] overflow-y-auto
          ${collapsed ? 'w-[60px]' : 'w-[220px]'}
        `}>
          {/* User mini-profile */}
          {!collapsed && (
            <div className="px-4 pt-4 pb-2 border-b">
              <div className="flex items-center gap-2">
                {user?.picture ? (
                  <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full object-cover shrink-0" />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-sm font-bold text-primary shrink-0">
                    {user?.name?.[0]?.toUpperCase()}
                  </div>
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate leading-tight">{user?.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{user?.user_type}</p>
                </div>
              </div>
            </div>
          )}

          <NavList />

          {/* Collapse toggle */}
          <div className="px-2 pb-3 border-t pt-2">
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="flex items-center justify-center w-full px-3 py-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors text-xs gap-1"
            >
              {collapsed ? <ChevronRight className="w-4 h-4" /> : <><ChevronLeft className="w-4 h-4" /><span>Collapse</span></>}
            </button>
          </div>
        </aside>

        {/* ── Mobile Drawer ── */}
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-[260px] p-0 flex flex-col overflow-hidden" aria-describedby={undefined}>
            {/* Header */}
            <SheetHeader className="px-4 pt-4 pb-3 border-b shrink-0">
              <SheetTitle className="flex items-center gap-2 text-base">
                <div className="w-8 h-8 bg-primary rounded-xl flex items-center justify-center">
                  <span className="text-lg font-bold text-primary-foreground leading-none">+</span>
                </div>
                {t('healthPortal')}
              </SheetTitle>
              <div className="flex items-center gap-2 mt-1">
                {user?.picture ? (
                  <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full object-cover shrink-0" />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-sm font-bold text-primary shrink-0">
                    {user?.name?.[0]?.toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 text-start">
                  <p className="text-sm font-medium truncate leading-tight">{user?.name}</p>
                  <p className="text-xs text-muted-foreground">{user?.user_type}</p>
                </div>
              </div>
            </SheetHeader>

            {/* Scrollable nav */}
            <div className="flex-1 min-h-0 overflow-y-auto">
              <NavList onSelect={() => setMobileOpen(false)} />
            </div>

            {/* Logout always pinned at bottom */}
            <div className="border-t p-3 shrink-0">
              <button
                onClick={() => { setMobileOpen(false); handleLogout(); }}
                className="flex items-center gap-2 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              >
                <LogOut className="w-4 h-4 shrink-0" /> {t('logout')}
              </button>
            </div>
          </SheetContent>
        </Sheet>

        {/* ── Main content ── */}
        <main className="flex-1 overflow-y-auto">
          <div className="container mx-auto px-4 py-6 max-w-5xl">
            {/* Profile header */}
            <div className="mb-6 flex items-center gap-4 p-4 rounded-xl bg-card border shadow-sm">
              <ProfilePictureUpload user={user} onUpdate={handleProfilePictureUpdate} size="lg" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap mb-0.5">
                  <h1 className="text-lg font-semibold truncate leading-tight">
                    {t('welcome')}, {user?.name}
                  </h1>
                  {user?.is_verified && (
                    <Badge className="bg-primary/90 text-xs px-2 py-0 h-5 shrink-0">
                      <BadgeCheck className="w-3 h-3 me-1" />{t('verified')}
                    </Badge>
                  )}
                  {user?.is_featured && (
                    <Badge className="bg-yellow-500 text-white text-xs px-2 py-0 h-5 shrink-0">
                      <Star className="w-3 h-3 me-1" />{t('featured')}
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground leading-tight">
                  {user?.user_type}
                  {user?.profile_data?.specialty && (
                    <span className="text-primary font-medium"> · {user.profile_data.specialty}</span>
                  )}
                </p>
              </div>
            </div>

            {renderContent()}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Dashboard;
