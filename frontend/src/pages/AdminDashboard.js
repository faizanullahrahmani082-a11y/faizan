import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  Users, ShoppingCart, Calendar, Activity, TrendingUp,
  CheckCircle, XCircle, Trash2, Shield, AlertTriangle, Search
} from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const StatCard = ({ icon: Icon, label, value, color = 'text-primary' }) => (
  <Card>
    <CardContent className="p-4 flex items-center gap-4">
      <div className={`p-3 rounded-full bg-muted ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="text-start">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold">{value ?? '–'}</p>
      </div>
    </CardContent>
  </Card>
);

const AdminDashboard = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [loading, setLoading] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const loadStats = async () => {
    try {
      const res = await api.get('/admin/stats');
      setStats(res.data);
    } catch (e) {
      if (e.response?.status === 403) {
        toast.error(t('adminOnly'));
        navigate('/dashboard');
      }
    }
  };

  const loadUsers = async (p = page) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: p, limit: 20 });
      if (search) params.append('search', search);
      if (filterType) params.append('user_type', filterType);
      const res = await api.get(`/admin/users?${params}`);
      setUsers(res.data.users || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      toast.error(t('error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadStats(); }, []);
  useEffect(() => { loadUsers(page); }, [page, filterType]);

  const handleSearch = (e) => {
    e.preventDefault();
    setPage(1);
    loadUsers(1);
  };

  const toggleVerify = async (userId, isVerified) => {
    try {
      await api.put(`/admin/users/${userId}/verify`);
      toast.success(isVerified ? t('userUnverified') : t('userVerified'));
      loadUsers(page);
      loadStats();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const toggleBan = async (userId, isBanned) => {
    try {
      await api.put(`/admin/users/${userId}/ban`);
      toast.success(isBanned ? t('userUnbanned') : t('userBanned'));
      loadUsers(page);
      loadStats();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    }
  };

  const deleteUser = async (userId) => {
    try {
      await api.delete(`/admin/users/${userId}`);
      toast.success(t('userDeleted'));
      setConfirmDeleteId(null);
      loadUsers(page);
      loadStats();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    }
  };

  const USER_TYPES = ['Doctor', 'Patient', 'Pharmacy', 'Biomedical Engineer'];
  const totalPages = Math.ceil(total / 20);

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-7 h-7 text-primary" />
            <h1 className="text-2xl font-bold">{t('adminDashboard')}</h1>
          </div>
          <Button variant="outline" onClick={() => navigate('/dashboard')}>← {t('dashboard')}</Button>
        </div>

        {/* Stats grid */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard icon={Users} label={t('totalUsers')} value={stats.total_users} />
            <StatCard icon={AlertTriangle} label={t('pendingVerifications')} value={stats.pending_verifications} color="text-yellow-500" />
            <StatCard icon={XCircle} label={t('bannedUsers')} value={stats.banned_users} color="text-red-500" />
            <StatCard icon={ShoppingCart} label={t('totalOrders2')} value={stats.total_orders} />
            <StatCard icon={Calendar} label={t('totalAppointments')} value={stats.total_appointments} />
            <StatCard icon={Activity} label="Service Tickets" value={stats.total_service_tickets} />
            <StatCard icon={TrendingUp} label={t('totalGmv')} value={`$${(stats.total_gmv || 0).toFixed(2)}`} color="text-green-500" />
            <StatCard icon={TrendingUp} label="Total Commission" value={`$${(stats.total_commission || 0).toFixed(2)}`} color="text-emerald-500" />
          </div>
        )}

        {/* Users by type */}
        {stats?.users_by_type && (
          <Card>
            <CardHeader><CardTitle className="text-start">{t('allUsers')} by Type</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              {Object.entries(stats.users_by_type).map(([type, count]) => (
                <div key={type} className="flex items-center gap-2 border rounded px-3 py-2">
                  <span className="text-sm font-medium">{type}</span>
                  <Badge>{count}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Users table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-start">{t('allUsers')}</CardTitle>
            <div className="flex flex-col sm:flex-row gap-2 mt-2">
              <form onSubmit={handleSearch} className="flex gap-2 flex-1">
                <Input
                  placeholder={t('searchUsers')}
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
                <Button type="submit"><Search className="w-4 h-4" /></Button>
              </form>
              <Select value={filterType} onValueChange={v => { setFilterType(v === 'all' ? '' : v); setPage(1); }}>
                <SelectTrigger className="w-48"><SelectValue placeholder={t('allTypes')} /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('allTypes')}</SelectItem>
                  {USER_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-center text-muted-foreground py-8">Loading...</p>
            ) : (
              <div className="space-y-2">
                {users.map(u => (
                  <div
                    key={u.user_id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between border rounded-lg p-3 gap-2"
                    data-testid={`admin-user-${u.user_id}`}
                  >
                    <div className="flex items-center gap-3 text-start min-w-0">
                      {u.picture ? (
                        <img src={u.picture} alt={u.name} className="w-9 h-9 rounded-full object-cover shrink-0" />
                      ) : (
                        <div className="w-9 h-9 rounded-full bg-primary/20 flex items-center justify-center font-bold text-primary shrink-0">
                          {u.name?.[0]?.toUpperCase()}
                        </div>
                      )}
                      <div className="min-w-0">
                        <p className="font-medium truncate">{u.name}</p>
                        <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                        <div className="flex flex-wrap gap-1 mt-1">
                          <Badge variant="outline" className="text-xs">{u.user_type}</Badge>
                          {u.is_verified && <Badge className="text-xs bg-emerald-500">✓ Verified</Badge>}
                          {u.is_banned && <Badge className="text-xs bg-red-500">Banned</Badge>}
                          {u.is_admin && <Badge className="text-xs bg-purple-500">Admin</Badge>}
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button
                        size="sm"
                        variant={u.is_verified ? 'outline' : 'default'}
                        onClick={() => toggleVerify(u.user_id, u.is_verified)}
                        disabled={u.is_admin}
                        title={u.is_verified ? t('unverifyUser') : t('verifyUser')}
                      >
                        <CheckCircle className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant={u.is_banned ? 'default' : 'outline'}
                        onClick={() => toggleBan(u.user_id, u.is_banned)}
                        disabled={u.is_admin}
                        title={u.is_banned ? t('unbanUser') : t('banUser')}
                        className={u.is_banned ? 'bg-orange-500 hover:bg-orange-600' : ''}
                      >
                        <XCircle className="w-4 h-4" />
                      </Button>
                      {confirmDeleteId === u.user_id ? (
                        <div className="flex gap-1">
                          <Button size="sm" variant="destructive" onClick={() => deleteUser(u.user_id)}>
                            {t('confirmDelete')}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setConfirmDeleteId(null)}>
                            {t('cancel')}
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirmDeleteId(u.user_id)}
                          disabled={u.is_admin}
                          title={t('deleteUser')}
                        >
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex justify-center gap-2 mt-4">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                  ←
                </Button>
                <span className="text-sm self-center">{page} / {totalPages}</span>
                <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                  →
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AdminDashboard;
