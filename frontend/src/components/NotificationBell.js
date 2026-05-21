import React, { useState, useEffect, useRef } from 'react';
import { useLanguage } from '../LanguageContext';
import { Button } from './ui/button';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Badge } from './ui/badge';
import { Bell, Check } from 'lucide-react';
import api from '../api';

const NotificationBell = () => {
  const { t } = useLanguage();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const lastSinceRef = useRef(null);

  const load = async () => {
    try {
      const params = lastSinceRef.current ? `?since=${encodeURIComponent(lastSinceRef.current)}` : '';
      const res = await api.get(`/notifications${params}`);
      if (params && res.data.notifications.length > 0) {
        setNotifications(prev => [...res.data.notifications, ...prev].slice(0, 50));
      } else if (!params) {
        setNotifications(res.data.notifications || []);
      }
      setUnreadCount(res.data.unread_count || 0);
      if (res.data.notifications.length > 0) {
        lastSinceRef.current = res.data.notifications[0].created_at;
      }
    } catch (e) {
      console.warn('Notification poll failed:', e?.message);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000); // poll every 15s
    return () => clearInterval(interval);
  }, []);

  const markRead = async (id) => {
    try {
      await api.put(`/notifications/${id}/read`);
      setNotifications(prev => prev.map(n => n.notification_id === id ? { ...n, is_read: true } : n));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (e) {
      console.error('Mark read failed:', e);
    }
  };

  const markAllRead = async () => {
    try {
      await api.put('/notifications/read-all');
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (e) {
      console.error('Mark all read failed:', e);
    }
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="relative" data-testid="notifications-bell">
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <Badge className="absolute -top-1 -end-1 h-5 w-5 p-0 flex items-center justify-center bg-accent text-accent-foreground text-xs">
              {unreadCount > 9 ? '9+' : unreadCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <div className="flex items-center justify-between p-3 border-b">
          <h3 className="font-semibold">{t('notifications')}</h3>
          {unreadCount > 0 && (
            <Button variant="ghost" size="sm" onClick={markAllRead} data-testid="mark-all-read-btn">
              <Check className="w-4 h-4 me-1" /> {t('markAllRead')}
            </Button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {notifications.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">{t('noNotifications')}</p>
          ) : (
            notifications.map(n => (
              <button
                key={n.notification_id}
                onClick={() => markRead(n.notification_id)}
                className={`w-full text-start p-3 hover:bg-muted border-b last:border-0 ${!n.is_read ? 'bg-primary/5' : ''}`}
                data-testid={`notification-${n.notification_id}`}
              >
                <div className="flex items-start gap-2">
                  {!n.is_read && <div className="w-2 h-2 bg-primary rounded-full mt-1.5 shrink-0" />}
                  <div className="flex-1">
                    <p className="font-medium text-sm">{n.title}</p>
                    <p className="text-xs text-muted-foreground">{n.message}</p>
                    <p className="text-xs text-muted-foreground mt-1">{new Date(n.created_at).toLocaleString()}</p>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default NotificationBell;
