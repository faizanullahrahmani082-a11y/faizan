import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Calendar } from './ui/calendar';
import { Badge } from './ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from './ui/alert-dialog';
import {
  Calendar as CalendarIcon, Video, MapPin, Clock, Building2,
  Award, HeartPulse, Search, CheckCircle2, Star,
  ChevronRight, X,
} from 'lucide-react';
import { formatPrice } from '../utils/currency';
import MedicalRecordTab from './MedicalRecordTab';
import api from '../api';
import { toast } from 'sonner';

const TIME_SLOTS = [
  '09:00', '09:30', '10:00', '10:30', '11:00', '11:30',
  '14:00', '14:30', '15:00', '15:30', '16:00', '16:30',
];

const STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  confirmed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  cancelled: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
};

const SPECIALTIES = [
  'General Practice', 'Cardiology', 'Dermatology', 'Endocrinology',
  'Gastroenterology', 'Neurology', 'Obstetrics & Gynecology', 'Ophthalmology',
  'Orthopedics', 'Pediatrics', 'Psychiatry', 'Pulmonology', 'Radiology',
  'Surgery', 'Urology', 'Internal Medicine', 'Emergency Medicine',
];

// ── Doctor Card ────────────────────────────────────────────────────────────────
const DoctorCard = ({ doc, selected, onSelect, t }) => {
  const pd = doc.profile_data || {};
  const initials = doc.name?.[0]?.toUpperCase() || '?';

  return (
    <button
      type="button"
      onClick={() => onSelect(doc)}
      className={`w-full text-left rounded-xl border p-4 transition-all hover:shadow-md focus:outline-none focus:ring-2 focus:ring-primary/50 ${
        selected
          ? 'border-primary bg-primary/5 shadow-md ring-2 ring-primary/30'
          : 'border-border bg-card hover:border-primary/40'
      }`}
      data-testid={`doctor-card-${doc.user_id}`}
    >
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="shrink-0">
          {doc.picture ? (
            <img src={doc.picture} alt={doc.name} className="w-12 h-12 rounded-full object-cover" />
          ) : (
            <div className="w-12 h-12 rounded-full bg-primary/15 flex items-center justify-center text-lg font-bold text-primary">
              {initials}
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-semibold text-sm truncate">{doc.name}</span>
            {doc.is_verified && (
              <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0" />
            )}
          </div>

          {pd.specialty && (
            <p className="text-xs text-primary font-medium mt-0.5">{pd.specialty}</p>
          )}

          <div className="mt-1.5 space-y-0.5">
            {pd.hospital && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Building2 className="w-3 h-3 shrink-0" />
                <span className="truncate">{pd.hospital}</span>
              </div>
            )}
            {pd.clinic_address && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <MapPin className="w-3 h-3 shrink-0" />
                <span className="truncate">{pd.clinic_address}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3 mt-2 flex-wrap">
            {pd.consultation_fee != null && (
              <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
                {formatPrice(pd.consultation_fee, pd.currency)}
              </span>
            )}
            {pd.years_experience != null && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Award className="w-3 h-3" /> {pd.years_experience} {t('yearsExperience')}
              </span>
            )}
            {doc.avg_rating > 0 && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />
                {doc.avg_rating.toFixed(1)} ({doc.total_reviews})
              </span>
            )}
          </div>
        </div>

        {selected && (
          <ChevronRight className="w-4 h-4 text-primary shrink-0 mt-1" />
        )}
      </div>
    </button>
  );
};

// ── Main component ─────────────────────────────────────────────────────────────
const AppointmentsTab = ({ user }) => {
  const { t } = useLanguage();
  const [appointments, setAppointments] = useState([]);

  // Doctor search / filter
  const [doctors, setDoctors] = useState([]);
  const [doctorsLoading, setDoctorsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterSpecialty, setFilterSpecialty] = useState('');
  const [filterCity, setFilterCity] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);

  // Booking form
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [date, setDate] = useState(new Date());
  const [time, setTime] = useState('');
  const [type, setType] = useState('video');
  const [notes, setNotes] = useState('');
  const [bookedSlots, setBookedSlots] = useState([]);

  const isPatient = user?.user_type === 'Patient';
  const [patientRecordId, setPatientRecordId] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');

  // ── Load appointments ───────────────────────────────────────────────────────
  const loadAppointments = async () => {
    try {
      const res = await api.get('/appointments/me');
      setAppointments(res.data.appointments || []);
    } catch (e) {
      console.error(e);
    }
  };

  // ── Load doctors with filters ───────────────────────────────────────────────
  const loadDoctors = async () => {
    setDoctorsLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery.trim()) params.set('search', searchQuery.trim());
      if (filterSpecialty && filterSpecialty !== '__all__') params.set('specialty', filterSpecialty);
      if (filterCity.trim()) params.set('city', filterCity.trim());
      if (verifiedOnly) params.set('verified_only', 'true');

      const res = await api.get(`/doctors?${params.toString()}`);
      setDoctors(res.data.doctors || []);
    } catch (e) {
      console.error(e);
      setDoctors([]);
    } finally {
      setDoctorsLoading(false);
    }
  };

  useEffect(() => {
    loadAppointments();
    if (isPatient) loadDoctors();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Debounced reload when text inputs change ────────────────────────────────
  useEffect(() => {
    if (!isPatient) return;
    const timer = setTimeout(() => loadDoctors(), 350);
    return () => clearTimeout(timer);
  }, [searchQuery, filterCity]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Immediate reload when selects/toggles change ────────────────────────────
  useEffect(() => {
    if (!isPatient) return;
    loadDoctors();
  }, [filterSpecialty, verifiedOnly]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Booked slots for selected doctor + date ─────────────────────────────────
  useEffect(() => {
    if (selectedDoctor && date) {
      const dateStr = date.toISOString().split('T')[0];
      api.get(`/appointments/doctor/${selectedDoctor.user_id}/booked-slots?date=${dateStr}`)
        .then(res => setBookedSlots(res.data.booked_slots || []))
        .catch(() => setBookedSlots([]));
    }
  }, [selectedDoctor, date]);

  const handleSelectDoctor = (doc) => {
    setSelectedDoctor(doc);
    setTime('');
    // Scroll to booking form
    setTimeout(() => {
      document.getElementById('booking-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  const handleClearDoctor = () => {
    setSelectedDoctor(null);
    setTime('');
  };

  const handleBook = async () => {
    if (!selectedDoctor || !time) {
      toast.error('Please select a doctor and a time slot');
      return;
    }
    try {
      const dateStr = date.toISOString().split('T')[0];
      const scheduledAt = `${dateStr}T${time}:00`;
      await api.post('/appointments', {
        doctor_id: selectedDoctor.user_id,
        scheduled_at: scheduledAt,
        appointment_type: type,
        notes,
      });
      toast.success(t('appointmentBooked'));
      setTime('');
      setNotes('');
      setSelectedDoctor(null);
      loadAppointments();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    }
  };

  const updateStatus = async (apptId, status) => {
    try {
      await api.put(`/appointments/${apptId}`, { status });
      toast.success('Status updated');
      loadAppointments();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const STATUS_FILTERS = ['all', 'pending', 'confirmed', 'completed', 'cancelled'];

  const filteredAppointments = statusFilter === 'all'
    ? appointments
    : appointments.filter(a => a.status === statusFilter);

  const startVideoCall = async (appt) => {
    try {
      let roomId = appt.video_room_id;
      if (!roomId) {
        const res = await api.post('/video/rooms', {
          appointment_id: appt.appointment_id,
          invitee_id: user.user_id === appt.doctor_id ? appt.patient_id : appt.doctor_id,
        });
        roomId = res.data.room_id;
      }
      window.location.href = `/video/${roomId}`;
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const bookedTimes = bookedSlots.map(s => s.scheduled_at.split('T')[1]?.substring(0, 5));

  return (
    <div className="space-y-6">

      {/* ── BOOK APPOINTMENT (patients only) ── */}
      {isPatient && (
        <Card data-testid="book-appointment-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-start">
              <CalendarIcon className="w-5 h-5" /> {t('bookAppointment')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">

            {/* ── Doctor search & filters ── */}
            <div className="space-y-3">
              <div className="grid sm:grid-cols-3 gap-2">
                {/* Search */}
                <div className="relative sm:col-span-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    className="pl-9"
                    placeholder={t('searchDoctors')}
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    data-testid="doctor-search-input"
                  />
                </div>

                {/* City */}
                <div className="relative">
                  <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    className="pl-9"
                    placeholder="City / district..."
                    value={filterCity}
                    onChange={e => setFilterCity(e.target.value)}
                    onBlur={loadDoctors}
                    data-testid="city-filter-input"
                  />
                </div>

                {/* Specialty */}
                <Select
                  value={filterSpecialty}
                  onValueChange={v => setFilterSpecialty(v)}
                  data-testid="specialty-filter"
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t('filterSpecialty')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All specialties</SelectItem>
                    {SPECIALTIES.map(s => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Verified toggle + result count */}
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setVerifiedOnly(v => !v)}
                  className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-full border transition-colors ${
                    verifiedOnly
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-transparent border-border text-muted-foreground hover:border-primary/50'
                  }`}
                  data-testid="verified-toggle"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {t('verified')} only
                </button>
                <span className="text-xs text-muted-foreground">
                  {doctorsLoading ? 'Loading…' : `${doctors.length} doctor${doctors.length !== 1 ? 's' : ''} found`}
                </span>
              </div>
            </div>

            {/* ── Doctor grid ── */}
            {doctors.length === 0 && !doctorsLoading ? (
              <p className="text-center text-sm text-muted-foreground py-6">{t('noDoctorsFound')}</p>
            ) : (
              <div className="grid sm:grid-cols-2 gap-3 max-h-80 overflow-y-auto pr-1">
                {doctors.map(doc => (
                  <DoctorCard
                    key={doc.user_id}
                    doc={doc}
                    selected={selectedDoctor?.user_id === doc.user_id}
                    onSelect={handleSelectDoctor}
                    t={t}
                  />
                ))}
              </div>
            )}

            {/* ── Booking form (shown after doctor selected) ── */}
            {selectedDoctor && (
              <div id="booking-form" className="border-t pt-5 space-y-4">
                {/* Selected doctor pill */}
                <div className="flex items-center gap-3 rounded-lg bg-primary/5 border border-primary/20 px-4 py-3">
                  {selectedDoctor.picture ? (
                    <img src={selectedDoctor.picture} alt={selectedDoctor.name} className="w-9 h-9 rounded-full object-cover" />
                  ) : (
                    <div className="w-9 h-9 rounded-full bg-primary/20 flex items-center justify-center text-sm font-bold text-primary">
                      {selectedDoctor.name?.[0]?.toUpperCase()}
                    </div>
                  )}
                  <div className="flex-1 text-start min-w-0">
                    <p className="font-semibold text-sm truncate">{selectedDoctor.name}</p>
                    {selectedDoctor.profile_data?.specialty && (
                      <p className="text-xs text-primary">{selectedDoctor.profile_data.specialty}</p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleClearDoctor}
                    className="p-1 rounded hover:bg-muted transition-colors"
                    aria-label="Clear selection"
                  >
                    <X className="w-4 h-4 text-muted-foreground" />
                  </button>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  {/* Calendar */}
                  <div>
                    <Label className="text-start block mb-2">{t('selectDate')}</Label>
                    <Calendar mode="single" selected={date} onSelect={setDate} className="rounded-md border" />
                  </div>

                  {/* Time + type + notes + book */}
                  <div className="space-y-3">
                    <div>
                      <Label className="text-start block mb-2">{t('selectTime')}</Label>
                      <div className="grid grid-cols-3 gap-2">
                        {TIME_SLOTS.map(slot => {
                          const isBooked = bookedTimes.includes(slot);
                          return (
                            <Button
                              key={slot}
                              variant={time === slot ? 'default' : 'outline'}
                              size="sm"
                              disabled={isBooked}
                              onClick={() => setTime(slot)}
                              data-testid={`time-slot-${slot}`}
                            >
                              {slot}
                            </Button>
                          );
                        })}
                      </div>
                    </div>

                    <div>
                      <Label className="text-start block mb-2">{t('appointmentType')}</Label>
                      <Select value={type} onValueChange={setType}>
                        <SelectTrigger data-testid="appointment-type-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="video">{t('video')}</SelectItem>
                          <SelectItem value="in-person">{t('inPerson')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label className="text-start block mb-2">{t('notes')}</Label>
                      <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="appointment-notes" />
                    </div>

                    <Button onClick={handleBook} className="w-full" data-testid="book-appointment-btn">
                      {t('book')}
                    </Button>
                  </div>
                </div>
              </div>
            )}

          </CardContent>
        </Card>
      )}

      {/* ── MY APPOINTMENTS ── */}
      <Card data-testid="my-appointments-card">
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <CardTitle className="text-start">{t('myAppointments')}</CardTitle>
            {/* Status filter pills */}
            <div className="flex flex-wrap gap-1.5">
              {STATUS_FILTERS.map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatusFilter(s)}
                  className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                    statusFilter === s
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-transparent border-border text-muted-foreground hover:border-primary/50'
                  }`}
                >
                  {s === 'all' ? t('all') : t(s)}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {filteredAppointments.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('noAppointments')}</p>
          ) : (
            <div className="space-y-3">
              {filteredAppointments.map(appt => (
                <div
                  key={appt.appointment_id}
                  className="border rounded-lg p-4 flex flex-col md:flex-row md:items-center justify-between gap-3"
                  data-testid={`appointment-${appt.appointment_id}`}
                >
                  <div className="flex-1 text-start">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium">
                        {isPatient ? appt.doctor_name : appt.patient_name}
                      </span>
                      <Badge className={STATUS_COLORS[appt.status]}>{t(appt.status)}</Badge>
                    </div>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {appt.scheduled_at.replace('T', ' ')}</span>
                      <span className="flex items-center gap-1">
                        {appt.appointment_type === 'video' ? <Video className="w-3 h-3" /> : <MapPin className="w-3 h-3" />}
                        {t(appt.appointment_type === 'video' ? 'video' : 'inPerson')}
                      </span>
                    </div>
                    {appt.notes && <p className="text-sm mt-1">{appt.notes}</p>}
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    {!isPatient && appt.status === 'pending' && (
                      <Button size="sm" onClick={() => updateStatus(appt.appointment_id, 'confirmed')} data-testid={`confirm-${appt.appointment_id}`}>
                        {t('confirm')}
                      </Button>
                    )}
                    {appt.status !== 'cancelled' && appt.status !== 'completed' && (
                      <Button size="sm" variant="outline" onClick={() => setCancelTarget(appt.appointment_id)} data-testid={`cancel-${appt.appointment_id}`}>
                        {t('cancel')}
                      </Button>
                    )}
                    {appt.status === 'confirmed' && appt.appointment_type === 'video' && (
                      <Button size="sm" variant="default" onClick={() => startVideoCall(appt)} data-testid={`join-video-${appt.appointment_id}`}>
                        <Video className="w-4 h-4 me-1" /> {t('joinVideo')}
                      </Button>
                    )}
                    {!isPatient && ['confirmed', 'pending'].includes(appt.status) && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setPatientRecordId(appt.patient_id)}
                        data-testid={`view-record-${appt.appointment_id}`}
                      >
                        <HeartPulse className="w-4 h-4 me-1" /> {t('viewRecord')}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cancel confirmation */}
      <AlertDialog open={!!cancelTarget} onOpenChange={o => !o && setCancelTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmCancel')}</AlertDialogTitle>
            <AlertDialogDescription>{t('confirmCancelMsg')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => { updateStatus(cancelTarget, 'cancelled'); setCancelTarget(null); }}
            >
              {t('confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Patient Medical Record dialog — for doctors */}
      <Dialog open={!!patientRecordId} onOpenChange={o => !o && setPatientRecordId(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" aria-describedby={undefined} data-testid="patient-record-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HeartPulse className="w-5 h-5 text-primary" /> {t('patientRecord')}
            </DialogTitle>
          </DialogHeader>
          {patientRecordId && (
            <MedicalRecordTab user={user} patientId={patientRecordId} readOnly />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AppointmentsTab;
