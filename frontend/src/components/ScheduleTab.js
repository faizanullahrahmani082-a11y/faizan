import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { CalendarDays, Plus, Trash2 } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

const ScheduleTab = () => {
  const { t } = useLanguage();
  const [slots, setSlots] = useState([]);

  const load = async () => {
    try {
      const res = await api.get('/schedule/me');
      setSlots(res.data.slots || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { load(); }, []);

  const addSlot = () => {
    setSlots([...slots, {
      day_of_week: 1,
      start_time: '09:00',
      end_time: '17:00',
      slot_duration_minutes: 30,
    }]);
  };

  const removeSlot = (idx) => {
    setSlots(slots.filter((_, i) => i !== idx));
  };

  const updateSlot = (idx, field, value) => {
    const newSlots = [...slots];
    newSlots[idx] = { ...newSlots[idx], [field]: value };
    setSlots(newSlots);
  };

  const save = async () => {
    try {
      await api.put('/schedule', { slots });
      toast.success('Schedule saved');
    } catch (e) {
      toast.error(t('error'));
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2"><CalendarDays className="w-5 h-5" /> {t('weeklyTemplate')}</CardTitle>
        <Button onClick={addSlot} data-testid="add-slot-btn"><Plus className="w-4 h-4 me-1" /> {t('addSlot')}</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {slots.length === 0 && (
          <p className="text-muted-foreground text-center py-8">{t('mySchedule')}</p>
        )}
        {slots.map((slot, idx) => (
          <div key={idx} className="border rounded-lg p-4 grid grid-cols-1 md:grid-cols-5 gap-3 items-end" data-testid={`schedule-slot-${idx}`}>
            <div>
              <Label className="text-start block text-xs">Day</Label>
              <Select value={String(slot.day_of_week)} onValueChange={(v) => updateSlot(idx, 'day_of_week', parseInt(v))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DAYS.map((d, i) => (
                    <SelectItem key={i} value={String(i)}>{t(d)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-start block text-xs">{t('startTime')}</Label>
              <Input type="time" value={slot.start_time} onChange={(e) => updateSlot(idx, 'start_time', e.target.value)} />
            </div>
            <div>
              <Label className="text-start block text-xs">{t('endTime')}</Label>
              <Input type="time" value={slot.end_time} onChange={(e) => updateSlot(idx, 'end_time', e.target.value)} />
            </div>
            <div>
              <Label className="text-start block text-xs">Slot (min)</Label>
              <Input type="number" value={slot.slot_duration_minutes} onChange={(e) => updateSlot(idx, 'slot_duration_minutes', parseInt(e.target.value))} />
            </div>
            <Button variant="destructive" size="sm" onClick={() => removeSlot(idx)} data-testid={`remove-slot-${idx}`}>
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        ))}
        {slots.length > 0 && (
          <Button onClick={save} className="w-full" data-testid="save-schedule-btn">{t('save')}</Button>
        )}
      </CardContent>
    </Card>
  );
};

export default ScheduleTab;
