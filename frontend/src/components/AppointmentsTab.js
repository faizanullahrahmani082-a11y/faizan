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
import { Calendar as CalendarIcon, Video, MapPin, Clock, Stethoscope, Building2, DollarSign, Award, HeartPulse } from 'lucide-react';
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

const AppointmentsTab = ({ user }) => {
  const { t } = useLanguage();
  const [appointments, setAppointments] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [selectedDoctor, setSelectedDoctor] = useState('');
  const [date, setDate] = useState(new Date());
  const [time, setTime] = useState('');
  const [type, setType] = useState('video');
  const [notes, setNotes] = useState('');
  const [bookedSlots, setBookedSlots] = useState([]);

  const isPatient = user?.user_type === 'Patient';
  const [patientRecordId, setPatientRecordId] = useState(null);

  const loadAppointments = async () => {
    try {
      const res = await api.get('/appointments/me');
      setAppointments(res.data.appointments || []);
    } catch (e) {
      console.error(e);
    }
  };

  const loadDoctors = async () => {
    try {
      // Get doctors using nearby with a generic location - we'll just list all doctors for demo
      const res = await api.get('/pharmacies/all'); // reusing - we need a doctor listing
      // Fall back: query users via locations
      const allRes = await api.get('/nearby?user_type=Doctor&latitude=34.5&longitude=69.2&radius_km=10000');
      setDoctors(allRes.data.results.map((r) => r.user));
    } catch (e) {
      console.error(e);
      setDoctors([]);
    }
  };

  useEffect(() => {
    loadAppointments();
    if (isPatient) loadDoctors();
  }, []);

  useEffect(() => {
    if (selectedDoctor && date) {
      const dateStr = date.toISOString().split('T')[0];
      api.get(`/appointments/doctor/${selectedDoctor}/booked-slots?date=${dateStr}`)
        .then(res => setBookedSlots(res.data.booked_slots || []))
        .catch(() => setBookedSlots([]));
    }
  }, [selectedDoctor, date]);

  const handleBook = async () => {
    if (!selectedDoctor || !time) {
      toast.error('Please select doctor and time');
      return;
    }
    try {
      const dateStr = date.toISOString().split('T')[0];
      const scheduledAt = `${dateStr}T${time}:00`;
      await api.post('/appointments', {
        doctor_id: selectedDoctor,
        scheduled_at: scheduledAt,
        appointment_type: type,
        notes,
      });
      toast.success(t('appointmentBooked'));
      setTime('');
      setNotes('');
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
      {isPatient && (
        <Card data-testid="book-appointment-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-start">
              <CalendarIcon className="w-5 h-5" /> {t('bookAppointment')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <Label className="text-start block mb-2">{t('selectDoctor')}</Label>
              <Select value={selectedDoctor} onValueChange={setSelectedDoctor}>
                <SelectTrigger data-testid="doctor-select"><SelectValue placeholder={t('selectDoctor')} /></SelectTrigger>
                <SelectContent>
                  {doctors.map(d => (
                    <SelectItem key={d.user_id} value={d.user_id}>
                      {d.name} {d.is_verified && '✓'} {d.profile_data?.specialty && `(${d.profile_data.specialty})`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Doctor info card */}
              {selectedDoctor && (() => {
                const doc = doctors.find(d => d.user_id === selectedDoctor);
                if (!doc) return null;
                const pd = doc.profile_data || {};
                return (
                  <div className="rounded-lg border bg-muted/40 p-4 space-y-3">
                    <div className="flex items-center gap-3">
                      {doc.picture ? (
                        <img src={doc.picture} alt={doc.name} className="w-12 h-12 rounded-full object-cover" />
                      ) : (
                        <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center text-lg font-bold text-primary">
                          {doc.name?.[0]?.toUpperCase()}
                        </div>
                      )}
                      <div className="text-start">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-sm">{doc.name}</span>
                          {doc.is_verified && <Badge className="bg-primary text-xs px-1 py-0">{t('verified')}</Badge>}
                        </div>
                        {pd.specialty && <p className="text-xs text-primary font-medium">{pd.specialty}</p>}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                      {pd.hospital && (
                        <div className="flex items-center gap-1">
                          <Building2 className="w-3 h-3 shrink-0" />
                          <span className="truncate">{pd.hospital}</span>
                        </div>
                      )}
                      {pd.years_experience != null && (
                        <div className="flex items-center gap-1">
                          <Award className="w-3 h-3 shrink-0" />
                          <span>{pd.years_experience} {t('yearsExperience')}</span>
                        </div>
                      )}
                      {pd.working_hours && (
                        <div className="flex items-center gap-1">
                          <Clock className="w-3 h-3 shrink-0" />
                          <span className="truncate">{pd.working_hours}</span>
                        </div>
                      )}
                      {pd.consultation_fee != null && (
                        <div className="flex items-center gap-1">
                          <DollarSign className="w-3 h-3 shrink-0" />
                          <span>{formatPrice(pd.consultation_fee, pd.currency)} {t('feePerConsultation')}</span>
                        </div>
                      )}
                    </div>

                    {pd.bio && (
                      <p className="text-xs text-muted-foreground text-start italic border-t pt-2 line-clamp-3">
                        {pd.bio}
                      </p>
                    )}
                  </div>
                );
              })()}
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <Label className="text-start block mb-2">{t('selectDate')}</Label>
                <Calendar mode="single" selected={date} onSelect={setDate} className="rounded-md border" />
              </div>
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
          </CardContent>
        </Card>
      )}

      <Card data-testid="my-appointments-card">
        <CardHeader>
          <CardTitle className="text-start">{t('myAppointments')}</CardTitle>
        </CardHeader>
        <CardContent>
          {appointments.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('noAppointments')}</p>
          ) : (
            <div className="space-y-3">
              {appointments.map(appt => (
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
                      <Button size="sm" variant="outline" onClick={() => updateStatus(appt.appointment_id, 'cancelled')} data-testid={`cancel-${appt.appointment_id}`}>
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
