import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Star, BadgeCheck, Check, Crown } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const SubscriptionTab = ({ user }) => {
  const { t } = useLanguage();
  const [plans, setPlans] = useState({});
  const [currentSub, setCurrentSub] = useState(null);
  const [cardNumber, setCardNumber] = useState('4242 4242 4242 4242');
  const [selectedPlan, setSelectedPlan] = useState('featured_monthly');
  const [loading, setLoading] = useState(false);

  const canSubscribe = ['Pharmacy', 'Doctor', 'Biomedical Engineer'].includes(user?.user_type);

  const load = async () => {
    try {
      const [plansRes, subRes] = await Promise.all([
        api.get('/subscriptions/plans'),
        api.get('/subscriptions/me'),
      ]);
      setPlans(plansRes.data.plans || {});
      setCurrentSub(subRes.data.subscription_id ? subRes.data : null);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { load(); }, []);

  const handleSubscribe = async () => {
    setLoading(true);
    try {
      const res = await api.post('/subscriptions/subscribe', {
        plan: selectedPlan,
        mock_card_number: cardNumber.replace(/\s/g, ''),
      });
      toast.success(res.data.message || t('paymentSuccess'));
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    try {
      await api.post('/subscriptions/cancel');
      toast.success('Subscription cancelled');
      load();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  if (!canSubscribe) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <Crown className="w-12 h-12 mx-auto text-muted-foreground mb-3" />
          <p className="text-muted-foreground">Premium subscription is available for Pharmacies, Doctors, and Biomedical Engineers.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {currentSub ? (
        <Card className="border-primary bg-gradient-to-br from-primary/5 to-secondary/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Crown className="w-5 h-5 text-primary" /> {currentSub.plan_name}
            </CardTitle>
            <CardDescription>{t('activeUntil')}: {currentSub.expires_at?.split('T')[0]}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge className="bg-primary text-primary-foreground"><BadgeCheck className="w-3 h-3 me-1" /> {t('verifiedBadge')}</Badge>
              <Badge className="bg-yellow-500 text-white"><Star className="w-3 h-3 me-1" /> {t('featuredListing')}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">Card ending in: ****{currentSub.mock_card_last4}</p>
            <Button variant="destructive" onClick={handleCancel} data-testid="cancel-subscription-btn">
              {t('cancelSubscription')}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-start">{t('premiumPlans')}</CardTitle>
              <CardDescription className="text-start">{t('mockPaymentNote')}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid md:grid-cols-2 gap-4">
                {Object.entries(plans).map(([key, plan]) => (
                  <Card
                    key={key}
                    onClick={() => setSelectedPlan(key)}
                    className={`cursor-pointer transition-all ${selectedPlan === key ? 'border-primary border-2 bg-primary/5' : ''}`}
                    data-testid={`plan-${key}`}
                  >
                    <CardContent className="p-6 text-start">
                      <h3 className="font-semibold text-lg">{plan.name}</h3>
                      <p className="text-3xl font-bold text-primary my-2">${plan.price_usd}</p>
                      <p className="text-sm text-muted-foreground mb-4">{plan.duration_days} days</p>
                      <ul className="space-y-2 text-sm">
                        <li className="flex items-center gap-2"><Check className="w-4 h-4 text-primary" /> {t('verifiedBadge')}</li>
                        <li className="flex items-center gap-2"><Check className="w-4 h-4 text-primary" /> {t('featuredListing')}</li>
                        <li className="flex items-center gap-2"><Check className="w-4 h-4 text-primary" /> {t('prioritySupport')}</li>
                      </ul>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-start">{t('cardNumber')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label className="text-start block">{t('cardNumber')}</Label>
                <Input
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                  data-testid="card-number-input"
                  placeholder="4242 4242 4242 4242"
                />
              </div>
              <Button onClick={handleSubscribe} disabled={loading} className="w-full" data-testid="subscribe-btn">
                {loading ? '...' : t('subscribeNow')}
              </Button>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
};

export default SubscriptionTab;
