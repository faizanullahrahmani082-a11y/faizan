import React, { useState, useEffect, useRef } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Stethoscope, Wrench, Send, Plus, AlertCircle } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const AIChatTab = ({ user }) => {
  const { t } = useLanguage();
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const isEngineerOrPharmacy = user?.user_type === 'Biomedical Engineer' || user?.user_type === 'Pharmacy' || user?.user_type === 'Doctor';

  const loadSessions = async () => {
    try {
      const res = await api.get('/chat/me');
      setSessions(res.data.sessions || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadSessions(); }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const startNewChat = async (chatType) => {
    try {
      const res = await api.post('/chat/start', { chat_type: chatType });
      setActiveSession(res.data);
      setMessages([]);
      loadSessions();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const openSession = async (sessionId) => {
    try {
      const res = await api.get(`/chat/${sessionId}`);
      setActiveSession(res.data);
      setMessages(res.data.messages || []);
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || !activeSession) return;
    const userMsg = { role: 'user', content: input, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    const text = input;
    setInput('');
    setLoading(true);
    try {
      const res = await api.post(`/chat/${activeSession.session_id}/message`, { text });
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.response, timestamp: new Date().toISOString() }]);
    } catch (e) {
      toast.error(t('error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid md:grid-cols-3 gap-4">
      <Card className="md:col-span-1">
        <CardHeader>
          <CardTitle className="text-start">{t('aiAssistant')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button onClick={() => startNewChat('symptom')} variant="outline" className="w-full justify-start" data-testid="start-symptom-chat">
            <Stethoscope className="w-4 h-4 me-2" /> {t('startChatSymptom')}
          </Button>
          {isEngineerOrPharmacy && (
            <Button onClick={() => startNewChat('device_fault')} variant="outline" className="w-full justify-start" data-testid="start-device-chat">
              <Wrench className="w-4 h-4 me-2" /> {t('startChatDevice')}
            </Button>
          )}

          <div className="pt-3 mt-3 border-t">
            <p className="text-xs text-muted-foreground mb-2 text-start">{t('newChat')}</p>
            {sessions.map(s => (
              <button
                key={s.session_id}
                onClick={() => openSession(s.session_id)}
                className={`w-full text-start p-2 rounded text-sm hover:bg-muted ${activeSession?.session_id === s.session_id ? 'bg-muted' : ''}`}
                data-testid={`chat-session-${s.session_id}`}
              >
                <div className="font-medium truncate">{s.title}</div>
                <div className="text-xs text-muted-foreground">{s.chat_type}</div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="md:col-span-2 flex flex-col" style={{ minHeight: '500px' }}>
        <CardHeader>
          <CardTitle className="text-start">{activeSession ? activeSession.title : t('aiAssistant')}</CardTitle>
          <div className="text-xs text-muted-foreground flex items-center gap-1 text-start">
            <AlertCircle className="w-3 h-3" /> {t('aiDisclaimer')}
          </div>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col">
          <div className="flex-1 overflow-y-auto space-y-3 mb-4" style={{ maxHeight: '400px' }}>
            {!activeSession && (
              <p className="text-muted-foreground text-center py-12">{t('chatPlaceholder')}</p>
            )}
            {messages.map((msg, idx) => (
              <div
                key={msg.timestamp ? `${msg.timestamp}-${msg.role}-${idx}` : idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                data-testid={`chat-msg-${idx}`}
              >
                <div className={`max-w-[80%] rounded-lg p-3 ${
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                }`}>
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-muted rounded-lg p-3">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {activeSession && (
            <div className="flex gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                placeholder={t('typeMessage')}
                disabled={loading}
                data-testid="chat-input"
              />
              <Button onClick={sendMessage} disabled={loading || !input.trim()} data-testid="chat-send-btn">
                <Send className="w-4 h-4" />
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AIChatTab;
