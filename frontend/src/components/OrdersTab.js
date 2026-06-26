import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { ShoppingCart, Package, DollarSign, TrendingUp, FileText } from 'lucide-react';
import api, { API } from '../api';
import { toast } from 'sonner';

const STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-blue-100 text-blue-800',
  shipped: 'bg-purple-100 text-purple-800',
  delivered: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-red-100 text-red-800',
};

const OrdersTab = ({ user }) => {
  const { t } = useLanguage();
  const [orders, setOrders] = useState([]);
  const [commission, setCommission] = useState(null);

  const isPharmacy = user?.user_type === 'Pharmacy';
  const isDoctor = user?.user_type === 'Doctor';

  const load = async () => {
    try {
      const res = await api.get('/orders/me');
      setOrders(res.data.orders || []);
      if (isPharmacy || isDoctor) {
        const cRes = await api.get('/commission/summary');
        setCommission(cRes.data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { load(); }, []);

  const updateStatus = async (orderId, status) => {
    try {
      await api.put(`/orders/${orderId}`, { status });
      toast.success('Status updated');
      load();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  return (
    <div className="space-y-6">
      {commission && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card data-testid="gmv-card">
            <CardContent className="p-6 text-start">
              <div className="flex items-center justify-between mb-2">
                <TrendingUp className="w-8 h-8 text-primary" />
                <Badge>{commission.role}</Badge>
              </div>
              <p className="text-sm text-muted-foreground">{t('totalGmv')}</p>
              <p className="text-3xl font-bold">${commission.gmv?.toFixed(2)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6 text-start">
              <DollarSign className="w-8 h-8 text-emerald-600 mb-2" />
              <p className="text-sm text-muted-foreground">{t('payoutTotal')}</p>
              <p className="text-3xl font-bold text-emerald-600">${commission.payout_total?.toFixed(2)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6 text-start">
              <Package className="w-8 h-8 text-accent mb-2" />
              <p className="text-sm text-muted-foreground">{t('commissionTotal')} ({(commission.commission_rate * 100).toFixed(0)}%)</p>
              <p className="text-3xl font-bold text-accent">${commission.commission_total?.toFixed(2)}</p>
            </CardContent>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-start"><ShoppingCart className="w-5 h-5" /> {t('myOrders')}</CardTitle>
        </CardHeader>
        <CardContent>
          {orders.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('noOrders')}</p>
          ) : (
            <div className="space-y-3">
              {orders.map(o => (
                <div key={o.order_id} className="border rounded-lg p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-start" data-testid={`order-${o.order_id}`}>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium">{o.medicine_name} × {o.quantity}</span>
                      <Badge className={STATUS_COLORS[o.status]}>{t(o.status)}</Badge>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {isPharmacy ? o.patient_name : o.pharmacy_name}
                    </div>
                    <div className="text-sm font-medium">
                      ${o.subtotal?.toFixed(2)}
                      {isPharmacy && <span className="text-xs text-muted-foreground font-normal ml-2">(payout: ${o.pharmacy_payout?.toFixed(2)})</span>}
                    </div>
                    {o.delivery_address && (
                      <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                        <Package className="w-3 h-3" /> {o.delivery_address}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2 flex-wrap justify-end">
                    {o.prescription_file_id && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => window.open(`${API}/files/${o.prescription_file_id}?auth=${localStorage.getItem('token')}`, '_blank')}
                        data-testid={`view-prescription-${o.order_id}`}
                      >
                        <FileText className="w-3.5 h-3.5 me-1" /> {t('viewPrescription')}
                      </Button>
                    )}
                    {isPharmacy && o.status === 'pending' && (
                      <Button size="sm" onClick={() => updateStatus(o.order_id, 'confirmed')} data-testid={`confirm-order-${o.order_id}`}>{t('confirm')}</Button>
                    )}
                    {isPharmacy && o.status === 'confirmed' && (
                      <Button size="sm" onClick={() => updateStatus(o.order_id, 'shipped')}>{t('shipped')}</Button>
                    )}
                    {isPharmacy && o.status === 'shipped' && (
                      <Button size="sm" onClick={() => updateStatus(o.order_id, 'delivered')}>{t('delivered')}</Button>
                    )}
                    {!isPharmacy && o.status === 'pending' && (
                      <Button size="sm" variant="outline" onClick={() => updateStatus(o.order_id, 'cancelled')}>{t('cancel')}</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default OrdersTab;
