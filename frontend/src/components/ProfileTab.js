import React, { useState } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Badge } from './ui/badge';
import { Stethoscope, Building2, Clock, DollarSign, Award, Phone, User, FileText, BadgeCheck, MapPin } from 'lucide-react';
import { CURRENCIES } from '../utils/currency';
import api from '../api';
import { toast } from 'sonner';

const SPECIALTIES = [
  'General Practice', 'Cardiology', 'Dermatology', 'Endocrinology',
  'Gastroenterology', 'Neurology', 'Obstetrics & Gynecology', 'Ophthalmology',
  'Orthopedics', 'Pediatrics', 'Psychiatry', 'Pulmonology', 'Radiology',
  'Surgery', 'Urology', 'Internal Medicine', 'Emergency Medicine', 'Other',
];

const Field = ({ label, icon: Icon, children }) => (
  <div>
    <Label className="text-start block mb-2">
      <span className="flex items-center gap-1">
        {Icon && <Icon className="w-3 h-3" />} {label}
      </span>
    </Label>
    {children}
  </div>
);

const ProfileTab = ({ user, onUpdate }) => {
  const { t } = useLanguage();
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState(user?.name || '');
  const [phone, setPhone] = useState(user?.phone || '');

  const pd = user?.profile_data || {};
  const [specialty, setSpecialty] = useState(pd.specialty || '');
  const [licenseNo, setLicenseNo] = useState(pd.license_no || '');
  const [hospital, setHospital] = useState(pd.hospital || '');
  const [yearsExp, setYearsExp] = useState(pd.years_experience ?? '');
  const [workingHours, setWorkingHours] = useState(pd.working_hours || '');
  const [fee, setFee] = useState(pd.consultation_fee ?? 30);
  const [currency, setCurrency] = useState(pd.currency || 'USD');
  const [bio, setBio] = useState(pd.bio || '');
  const [clinicAddress, setClinicAddress] = useState(pd.clinic_address || '');

  const isDoctor = user?.user_type === 'Doctor';

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { name, phone };
      if (isDoctor) {
        payload.profile_data = {
          specialty: specialty || null,
          license_no: licenseNo || null,
          hospital: hospital || null,
          years_experience: yearsExp !== '' ? parseInt(yearsExp) : null,
          working_hours: workingHours || null,
          consultation_fee: parseFloat(fee) || 30,
          currency,
          bio: bio || null,
          clinic_address: clinicAddress || null,
        };
      }
      const res = await api.put('/profile', payload);
      onUpdate(res.data);
      toast.success(t('profileSaved'));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">

      {/* Profile summary banner */}
      <Card className="bg-gradient-to-r from-primary/10 to-primary/5 border-primary/20">
        <CardContent className="pt-5 pb-4">
          <div className="flex items-center gap-4">
            {user?.picture ? (
              <img src={user.picture} alt={user.name} className="w-16 h-16 rounded-full object-cover border-2 border-primary/30" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center text-2xl font-bold text-primary">
                {user?.name?.[0]?.toUpperCase() || '?'}
              </div>
            )}
            <div className="text-start">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-semibold">{user?.name}</h2>
                {user?.is_verified && (
                  <Badge className="bg-primary text-xs">
                    <BadgeCheck className="w-3 h-3 me-1" />{t('verified')}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">{user?.user_type}</p>
              {isDoctor && pd.specialty && (
                <p className="text-sm font-medium text-primary">{pd.specialty}</p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Basic info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-start text-base">
            <User className="w-4 h-4" /> {t('personalInfo')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Field label={t('name')} icon={User}>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label={t('phone')} icon={Phone}>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+93 7XX XXX XXX" />
            </Field>
          </div>
          <p className="text-xs text-muted-foreground text-start">Email : {user?.email}</p>
        </CardContent>
      </Card>

      {/* Doctor professional info */}
      {isDoctor && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-start text-base">
              <Stethoscope className="w-4 h-4" /> {t('professionalInfo')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <Field label={t('specialty')} icon={Stethoscope}>
                <Select value={specialty} onValueChange={setSpecialty}>
                  <SelectTrigger>
                    <SelectValue placeholder={t('selectSpecialty')} />
                  </SelectTrigger>
                  <SelectContent>
                    {SPECIALTIES.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field label={t('licenseNo')} icon={Award}>
                <Input value={licenseNo} onChange={(e) => setLicenseNo(e.target.value)} placeholder="MED-XXXXX" />
              </Field>

              <Field label={t('hospital')} icon={Building2}>
                <Input value={hospital} onChange={(e) => setHospital(e.target.value)} placeholder="Hospital / Clinic" />
              </Field>

              <Field label={t('clinicAddress')} icon={MapPin}>
                <Input value={clinicAddress} onChange={(e) => setClinicAddress(e.target.value)} placeholder="Street, District, City" />
              </Field>

              <Field label={t('yearsExperience')}>
                <Input
                  type="number" min="0" max="60"
                  value={yearsExp}
                  onChange={(e) => setYearsExp(e.target.value)}
                  placeholder="e.g. 10"
                />
              </Field>

              <Field label={t('workingHours')} icon={Clock}>
                <Input value={workingHours} onChange={(e) => setWorkingHours(e.target.value)} placeholder="Mon-Fri 09:00-17:00" />
              </Field>

              <Field label={t('consultationFee')} icon={DollarSign}>
                <div className="flex gap-2">
                  <Select value={currency} onValueChange={setCurrency}>
                    <SelectTrigger className="w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CURRENCIES.map((c) => (
                        <SelectItem key={c.code} value={c.code}>
                          {c.symbol} {c.code}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    type="number" min="0" step="0.5"
                    value={fee}
                    onChange={(e) => setFee(e.target.value)}
                    className="flex-1"
                  />
                </div>
              </Field>
            </div>

            <Field label={t('bio')} icon={FileText}>
              <Textarea
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                placeholder={t('bioPlaceholder')}
                rows={4}
              />
            </Field>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving} size="lg">
          {saving ? t('saving') : t('saveProfile')}
        </Button>
      </div>
    </div>
  );
};

export default ProfileTab;
