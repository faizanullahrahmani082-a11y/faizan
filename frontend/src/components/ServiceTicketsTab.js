import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Wrench, Plus, ClipboardList } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const URGENCY_COLORS = {
  normal: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  urgent: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  critical: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
};

const STATUS_COLORS = {
  open: 'bg-emerald-100 text-emerald-800',
  accepted: 'bg-blue-100 text-blue-800',
  in_progress: 'bg-purple-100 text-purple-800',
  completed: 'bg-gray-100 text-gray-800',
  cancelled: 'bg-red-100 text-red-800',
};

const DEVICE_TYPES = ['MRI', 'X-Ray', 'Ultrasound', 'CT Scan', 'ECG', 'Ventilator', 'Defibrillator', 'Infusion Pump', 'Patient Monitor', 'Other'];

const ServiceTicketsTab = ({ user }) => {
  const { t } = useLanguage();
  const isEngineer = user?.user_type === 'Biomedical Engineer';
  const [myTickets, setMyTickets] = useState([]);
  const [openTickets, setOpenTickets] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    device_type: '', issue_description: '', location: '', urgency: 'normal', contact_phone: ''
  });
  const [activeTab, setActiveTab] = useState(isEngineer ? 'open' : 'my');
  const [engineerNotes, setEngineerNotes] = useState({});

  const loadMyTickets = async () => {
    try {
      const res = await api.get('/service-tickets/me');
      setMyTickets(res.data.tickets || []);
    } catch (e) {
      console.error(e);
    }
  };

  const loadOpenTickets = async () => {
    if (!isEngineer) return;
    try {
      const res = await api.get('/service-tickets/available');
      setOpenTickets(res.data.tickets || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadMyTickets();
    loadOpenTickets();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await api.post('/service-tickets', form);
      toast.success(t('ticketCreated'));
      setShowForm(false);
      setForm({ device_type: '', issue_description: '', location: '', urgency: 'normal', contact_phone: '' });
      loadMyTickets();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    }
  };

  const handleAccept = async (ticketId) => {
    try {
      await api.put(`/service-tickets/${ticketId}`, { status: 'accepted' });
      toast.success(t('ticketAccepted'));
      loadOpenTickets();
      loadMyTickets();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    }
  };

  const handleUpdateStatus = async (ticketId, status) => {
    try {
      const notes = engineerNotes[ticketId];
      await api.put(`/service-tickets/${ticketId}`, { status, engineer_notes: notes });
      toast.success('Updated');
      loadMyTickets();
      loadOpenTickets();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const TicketCard = ({ ticket, showAccept = false }) => (
    <div
      key={ticket.ticket_id}
      className="border rounded-lg p-4 space-y-2"
      data-testid={`ticket-${ticket.ticket_id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-start">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold">{ticket.device_type}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${URGENCY_COLORS[ticket.urgency] || ''}`}>
              {ticket.urgency}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[ticket.status] || ''}`}>
              {ticket.status}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{ticket.issue_description}</p>
          {ticket.location && <p className="text-xs text-muted-foreground">📍 {ticket.location}</p>}
          {ticket.requester_name && <p className="text-xs text-muted-foreground">By: {ticket.requester_name}</p>}
          {ticket.engineer_name && <p className="text-xs text-muted-foreground">Engineer: {ticket.engineer_name}</p>}
          {ticket.engineer_notes && (
            <p className="text-xs text-muted-foreground border-t pt-1 mt-1">Notes: {ticket.engineer_notes}</p>
          )}
          <p className="text-xs text-muted-foreground">{new Date(ticket.created_at).toLocaleString()}</p>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          {showAccept && ticket.status === 'open' && (
            <Button size="sm" onClick={() => handleAccept(ticket.ticket_id)}>
              {t('acceptTicket')}
            </Button>
          )}
          {!showAccept && isEngineer && ticket.engineer_id === user?.user_id && ticket.status === 'accepted' && (
            <Button size="sm" onClick={() => handleUpdateStatus(ticket.ticket_id, 'in_progress')}>
              Start
            </Button>
          )}
          {!showAccept && isEngineer && ticket.engineer_id === user?.user_id && ticket.status === 'in_progress' && (
            <Button size="sm" variant="outline" onClick={() => handleUpdateStatus(ticket.ticket_id, 'completed')}>
              Complete
            </Button>
          )}
        </div>
      </div>
      {isEngineer && ticket.engineer_id === user?.user_id && ['accepted', 'in_progress'].includes(ticket.status) && (
        <div className="flex gap-2">
          <Input
            placeholder={t('engineerNotes')}
            value={engineerNotes[ticket.ticket_id] || ''}
            onChange={e => setEngineerNotes(prev => ({ ...prev, [ticket.ticket_id]: e.target.value }))}
            className="text-xs"
          />
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Create ticket (non-engineers) */}
      {!isEngineer && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Wrench className="w-5 h-5" /> {t('serviceTickets')}
            </CardTitle>
            <Button onClick={() => setShowForm(!showForm)} size="sm">
              <Plus className="w-4 h-4 me-1" /> {t('createTicket')}
            </Button>
          </CardHeader>
          {showForm && (
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-3">
                <div className="grid md:grid-cols-2 gap-3">
                  <div>
                    <Label className="text-start block">{t('deviceType')} *</Label>
                    <Select value={form.device_type} onValueChange={v => setForm({ ...form, device_type: v })}>
                      <SelectTrigger><SelectValue placeholder="Select device..." /></SelectTrigger>
                      <SelectContent>
                        {DEVICE_TYPES.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-start block">{t('urgency')}</Label>
                    <Select value={form.urgency} onValueChange={v => setForm({ ...form, urgency: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="normal">{t('urgencyNormal')}</SelectItem>
                        <SelectItem value="urgent">{t('urgencyUrgent')}</SelectItem>
                        <SelectItem value="critical">{t('urgencyCritical')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-start block">Location</Label>
                    <Input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} placeholder="Hospital / clinic name" />
                  </div>
                  <div>
                    <Label className="text-start block">{t('contactPhone')}</Label>
                    <Input value={form.contact_phone} onChange={e => setForm({ ...form, contact_phone: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label className="text-start block">{t('issueDescription')} *</Label>
                  <Textarea
                    value={form.issue_description}
                    onChange={e => setForm({ ...form, issue_description: e.target.value })}
                    required
                    placeholder="Describe the issue in detail..."
                  />
                </div>
                <Button type="submit">{t('createTicket')}</Button>
              </form>
            </CardContent>
          )}
        </Card>
      )}

      {/* Tabs for engineer */}
      {isEngineer && (
        <div className="flex gap-2">
          <Button
            variant={activeTab === 'open' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setActiveTab('open')}
          >
            {t('openTickets')} ({openTickets.length})
          </Button>
          <Button
            variant={activeTab === 'my' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setActiveTab('my')}
          >
            {t('myTickets')} ({myTickets.length})
          </Button>
        </div>
      )}

      {/* Open tickets (engineers) */}
      {isEngineer && activeTab === 'open' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-start">
              <ClipboardList className="w-5 h-5" /> {t('openTickets')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {openTickets.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">{t('noTickets')}</p>
            ) : (
              openTickets.map(ticket => <TicketCard key={ticket.ticket_id} ticket={ticket} showAccept={true} />)
            )}
          </CardContent>
        </Card>
      )}

      {/* My tickets */}
      {(!isEngineer || activeTab === 'my') && (
        <Card>
          <CardHeader>
            <CardTitle className="text-start">{t('myTickets')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {myTickets.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">{t('noTickets')}</p>
            ) : (
              myTickets.map(ticket => <TicketCard key={ticket.ticket_id} ticket={ticket} showAccept={false} />)
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ServiceTicketsTab;
