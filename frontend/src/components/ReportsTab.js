import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { FileText, Mail, TrendingUp, Star, Package } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const ReportsTab = ({ user }) => {
  const { t } = useLanguage();
  const [currentReport, setCurrentReport] = useState(null);
  const [savedReports, setSavedReports] = useState([]);
  const [loading, setLoading] = useState(false);
  const [consultationFee, setConsultationFee] = useState(user?.profile_data?.consultation_fee || 30);

  const isDoctor = user?.user_type === 'Doctor';

  const loadReports = async () => {
    try {
      const [current, list] = await Promise.all([
        api.get('/reports/monthly'),
        api.get('/reports/me'),
      ]);
      setCurrentReport(current.data);
      setSavedReports(list.data.reports || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadReports(); }, []);

  const sendReport = async () => {
    setLoading(true);
    try {
      await api.post('/reports/monthly/send');
      toast.success(t('reportSentMock'));
      loadReports();
    } catch (e) {
      toast.error(t('error'));
    } finally {
      setLoading(false);
    }
  };

  const saveFee = async () => {
    try {
      await api.put('/profile', {
        profile_data: { consultation_fee: parseFloat(consultationFee) }
      });
      toast.success('Consultation fee updated');
    } catch (e) {
      toast.error(t('error'));
    }
  };

  return (
    <div className="space-y-6">
      {isDoctor && (
        <Card className="border-primary/30 bg-gradient-to-br from-primary/5 to-transparent">
          <CardHeader>
            <CardTitle className="text-start">{t('consultationFee')}</CardTitle>
            <CardDescription className="text-start">Set your per-consultation fee. Platform takes 12% commission.</CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2 items-end">
            <div className="flex-1">
              <Label className="text-start block">{t('consultationFee')}</Label>
              <Input type="number" step="0.01" value={consultationFee} onChange={(e) => setConsultationFee(e.target.value)} data-testid="consultation-fee-input" />
            </div>
            <Button onClick={saveFee} data-testid="save-fee-btn">{t('save')}</Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-start flex items-center gap-2">
              <FileText className="w-5 h-5" /> {t('monthlyReports')}
            </CardTitle>
            <CardDescription className="text-start mt-1">
              {currentReport?.period && `Period: ${currentReport.period}`}
            </CardDescription>
          </div>
          <Button onClick={sendReport} disabled={loading} data-testid="send-report-btn">
            <Mail className="w-4 h-4 me-1" /> {loading ? '...' : t('sendReport')}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {currentReport && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardContent className="p-4 text-start">
                  <TrendingUp className="w-6 h-6 text-primary mb-2" />
                  <p className="text-xs text-muted-foreground">{t('totalGmv')}</p>
                  <p className="text-2xl font-bold">${(currentReport.gmv || 0).toFixed(2)}</p>
                </CardContent>
              </Card>
              {currentReport.total_orders !== undefined && (
                <Card>
                  <CardContent className="p-4 text-start">
                    <Package className="w-6 h-6 text-secondary mb-2" />
                    <p className="text-xs text-muted-foreground">{t('totalOrders')}</p>
                    <p className="text-2xl font-bold">{currentReport.total_orders}</p>
                  </CardContent>
                </Card>
              )}
              {currentReport.completed_consultations !== undefined && (
                <Card>
                  <CardContent className="p-4 text-start">
                    <Package className="w-6 h-6 text-secondary mb-2" />
                    <p className="text-xs text-muted-foreground">Completed Consultations</p>
                    <p className="text-2xl font-bold">{currentReport.completed_consultations}</p>
                  </CardContent>
                </Card>
              )}
              {currentReport.avg_rating !== undefined && currentReport.avg_rating > 0 && (
                <Card>
                  <CardContent className="p-4 text-start">
                    <Star className="w-6 h-6 text-accent mb-2" />
                    <p className="text-xs text-muted-foreground">{t('avgRating')}</p>
                    <p className="text-2xl font-bold">{currentReport.avg_rating} / 5</p>
                    <p className="text-xs text-muted-foreground">{currentReport.total_reviews} reviews</p>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {currentReport?.top_medicines?.length > 0 && (
            <div>
              <h4 className="font-semibold mb-2 text-start">{t('topMedicines')}</h4>
              <div className="space-y-2">
                {currentReport.top_medicines.map((m, idx) => (
                  <div key={m.name || `top-${idx}`} className="flex items-center justify-between border rounded p-3">
                    <span className="font-medium">{idx + 1}. {m.name}</span>
                    <div className="flex gap-4 text-sm text-muted-foreground">
                      <span>{m.quantity} units</span>
                      <span className="font-medium text-primary">${m.revenue?.toFixed(2)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-start">Sent Reports</CardTitle>
        </CardHeader>
        <CardContent>
          {savedReports.length === 0 ? (
            <p className="text-muted-foreground text-center py-6">{t('noReports')}</p>
          ) : (
            <div className="space-y-2">
              {savedReports.map(r => (
                <div key={r.report_id} className="flex items-center justify-between border rounded p-3" data-testid={`report-${r.report_id}`}>
                  <div className="text-start">
                    <p className="font-medium">{r.period}</p>
                    <p className="text-xs text-muted-foreground">{new Date(r.sent_at).toLocaleString()}</p>
                  </div>
                  <Badge>{r.delivery_status}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ReportsTab;
