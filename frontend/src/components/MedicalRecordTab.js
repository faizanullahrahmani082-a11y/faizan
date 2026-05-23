import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Shield, Plus, X, HeartPulse, Phone, Pill, AlertTriangle } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const TagInput = ({ label, items, onChange, placeholder }) => {
  const [input, setInput] = useState('');
  const add = () => {
    const v = input.trim();
    if (v && !items.includes(v)) { onChange([...items, v]); setInput(''); }
  };
  return (
    <div>
      <Label className="text-start block mb-1">{label}</Label>
      <div className="flex flex-wrap gap-1 mb-2">
        {items.map((item, i) => (
          <Badge key={i} variant="secondary" className="gap-1">
            {item}
            <button type="button" onClick={() => onChange(items.filter((_, j) => j !== i))}>
              <X className="w-3 h-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder={placeholder}
        />
        <Button type="button" size="sm" variant="outline" onClick={add}>
          <Plus className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
};

const MedicalRecordTab = ({ user, patientId = null, readOnly = false }) => {
  const { t } = useLanguage();
  const isDoctor = user?.user_type === 'Doctor';
  const targetPatientId = patientId || (user?.user_type === 'Patient' ? user.user_id : null);

  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    allergies: [],
    current_medications: [],
    emergency_contact_name: '',
    emergency_contact_phone: '',
    notes: '',
  });

  const loadRecord = async () => {
    if (!targetPatientId) { setLoading(false); return; }
    setLoading(true);
    try {
      const url = isDoctor && patientId ? `/medical-record/${patientId}` : '/medical-record/me';
      const res = await api.get(url);
      const r = res.data;
      setRecord(r);
      setForm({
        allergies: r.allergies || [],
        current_medications: r.current_medications || [],
        emergency_contact_name: r.emergency_contact_name || '',
        emergency_contact_phone: r.emergency_contact_phone || '',
        notes: r.notes || '',
      });
    } catch (e) {
      if (e.response?.status === 403) {
        toast.error(e.response.data?.detail || t('error'));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadRecord(); }, [targetPatientId]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put('/medical-record/me', form);
      toast.success(t('medicalRecordSaved'));
      loadRecord();
    } catch (e) {
      toast.error(t('error'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="text-center text-muted-foreground py-8">Loading...</p>;

  if (!targetPatientId) {
    return <p className="text-center text-muted-foreground py-8">{t('error')}</p>;
  }

  return (
    <div className="space-y-4">
      <Card className="border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-start">
            <HeartPulse className="w-5 h-5 text-primary" /> {t('medicalRecord')}
          </CardTitle>
          <CardDescription className="text-start">
            {isDoctor
              ? `${t('patientRecord')}: ${record?.patient_name || patientId}`
              : t('medicalRecordDesc')}
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Doctor view (read-only) */}
      {isDoctor && patientId && (
        <div className="grid md:grid-cols-2 gap-4">
          <Card>
            <CardContent className="p-4 space-y-3">
              <h4 className="font-semibold text-start flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500" /> Allergies
              </h4>
              {form.allergies.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('noneRecorded')}</p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {form.allergies.map((a, i) => (
                    <Badge key={i} variant="destructive" className="text-xs">{a}</Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 space-y-3">
              <h4 className="font-semibold text-start flex items-center gap-2">
                <Pill className="w-4 h-4 text-blue-500" /> {t('currentMedications')}
              </h4>
              {form.current_medications.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('noneRecorded')}</p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {form.current_medications.map((m, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">{m}</Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-start space-y-2">
              <h4 className="font-semibold flex items-center gap-2">
                <HeartPulse className="w-4 h-4 text-primary" /> {t('clinicalProfile')}
              </h4>
              {record?.blood_type && <p className="text-sm"><span className="text-muted-foreground">Blood type:</span> <strong>{record.blood_type}</strong></p>}
              {record?.age && <p className="text-sm"><span className="text-muted-foreground">Age:</span> {record.age}</p>}
              {record?.gender && <p className="text-sm"><span className="text-muted-foreground">Gender:</span> {record.gender}</p>}
              {record?.chronic_illnesses?.length > 0 && (
                <div>
                  <p className="text-sm text-muted-foreground">Chronic:</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {record.chronic_illnesses.map((c, i) => (
                      <Badge key={i} variant="outline" className="text-xs">{c}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-start space-y-2">
              <h4 className="font-semibold flex items-center gap-2">
                <Phone className="w-4 h-4 text-green-500" /> {t('emergencyContact')}
              </h4>
              {record?.emergency_contact_name ? (
                <>
                  <p className="text-sm">{record.emergency_contact_name}</p>
                  {record?.emergency_contact_phone && (
                    <p className="text-sm text-primary">{record.emergency_contact_phone}</p>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{t('noneRecorded')}</p>
              )}
            </CardContent>
          </Card>
          {record?.notes && (
            <Card className="md:col-span-2">
              <CardContent className="p-4 text-start">
                <h4 className="font-semibold mb-2">Notes</h4>
                <p className="text-sm text-muted-foreground italic">{record.notes}</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Patient editable form */}
      {!isDoctor && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground border rounded p-2 bg-muted/30">
            <Shield className="w-4 h-4 text-primary shrink-0" />
            {t('medicalRecordEncrypted')}
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <TagInput
              label={`⚠️ Allergies`}
              items={form.allergies}
              onChange={v => setForm({ ...form, allergies: v })}
              placeholder="e.g. Penicillin, Aspirin..."
            />
            <TagInput
              label={`💊 ${t('currentMedications')}`}
              items={form.current_medications}
              onChange={v => setForm({ ...form, current_medications: v })}
              placeholder="e.g. Metformin 500mg..."
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <Label className="text-start block mb-1">{t('emergencyContactName')}</Label>
              <Input
                value={form.emergency_contact_name}
                onChange={e => setForm({ ...form, emergency_contact_name: e.target.value })}
                placeholder="Full name"
              />
            </div>
            <div>
              <Label className="text-start block mb-1">{t('emergencyContactPhone')}</Label>
              <Input
                value={form.emergency_contact_phone}
                onChange={e => setForm({ ...form, emergency_contact_phone: e.target.value })}
                placeholder="+93 7xx xxx xxx"
              />
            </div>
          </div>

          <div>
            <Label className="text-start block mb-1">Notes for doctor</Label>
            <Textarea
              value={form.notes}
              onChange={e => setForm({ ...form, notes: e.target.value })}
              placeholder="Anything your doctor should know..."
              rows={3}
            />
          </div>

          <Button onClick={handleSave} disabled={saving}>
            {saving ? t('saving') : t('saveMedicalRecord')}
          </Button>
        </div>
      )}
    </div>
  );
};

export default MedicalRecordTab;
