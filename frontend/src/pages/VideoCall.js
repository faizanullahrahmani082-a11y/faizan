import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Video, VideoOff, Mic, MicOff, PhoneOff } from 'lucide-react';
import SimplePeer from 'simple-peer';
import api from '../api';
import { toast } from 'sonner';

const VideoCall = () => {
  const { t } = useLanguage();
  const { roomId } = useParams();
  const navigate = useNavigate();
  const [localStream, setLocalStream] = useState(null);
  const [audioOn, setAudioOn] = useState(true);
  const [videoOn, setVideoOn] = useState(true);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState('connecting');
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const peerRef = useRef(null);
  const lastSignalTimestampRef = useRef(null);
  const pollIntervalRef = useRef(null);
  const userRef = useRef(null);
  const roomRef = useRef(null);

  useEffect(() => {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    userRef.current = user;
    init();
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cleanup = () => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    if (peerRef.current) peerRef.current.destroy();
    if (localStream) localStream.getTracks().forEach(t => t.stop());
  };

  const init = async () => {
    try {
      // Get local media
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      setLocalStream(stream);
      if (localVideoRef.current) localVideoRef.current.srcObject = stream;

      // Join room
      const joinRes = await api.post(`/video/rooms/${roomId}/join`);
      roomRef.current = joinRes.data;

      const isInitiator = roomRef.current.host_id === userRef.current.user_id;
      const targetId = isInitiator ? roomRef.current.invitee_id : roomRef.current.host_id;

      if (!targetId) {
        setStatus('waitingForPeer');
        // Start polling for new participants
        pollIntervalRef.current = setInterval(() => pollSignals(stream, isInitiator), 2000);
        return;
      }

      createPeer(stream, isInitiator, targetId);
      pollIntervalRef.current = setInterval(() => pollSignals(stream, isInitiator), 2000);
    } catch (e) {
      console.error('Init error:', e);
      toast.error('Camera/microphone access required');
      setStatus('error');
    }
  };

  const createPeer = (stream, isInitiator, targetId) => {
    const peer = new SimplePeer({
      initiator: isInitiator,
      trickle: true,
      stream,
      config: {
        iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:global.stun.twilio.com:3478' },
        ],
      },
    });

    peer.on('signal', async (data) => {
      try {
        await api.post(`/video/rooms/${roomId}/signal`, {
          signal_data: data,
          target_user_id: targetId,
        });
      } catch (e) {
        console.error('Signal send error:', e);
      }
    });

    peer.on('stream', (remoteStream) => {
      if (remoteVideoRef.current) {
        remoteVideoRef.current.srcObject = remoteStream;
        setConnected(true);
        setStatus('connected');
      }
    });

    peer.on('error', (err) => {
      console.error('Peer error:', err);
    });

    peer.on('close', () => {
      setConnected(false);
      setStatus('disconnected');
    });

    peerRef.current = peer;
  };

  const pollSignals = async (stream, isInitiator) => {
    try {
      const params = lastSignalTimestampRef.current ? `?since=${encodeURIComponent(lastSignalTimestampRef.current)}` : '';
      const res = await api.get(`/video/rooms/${roomId}/signals${params}`);
      const signals = res.data.signals || [];
      for (const sig of signals) {
        if (!peerRef.current) {
          // Late peer creation if no invitee was set initially
          createPeer(stream, isInitiator, sig.from_user_id);
        }
        if (peerRef.current && !peerRef.current.destroyed) {
          peerRef.current.signal(sig.signal_data);
        }
        lastSignalTimestampRef.current = sig.timestamp;
      }
    } catch (e) {
      console.error('Poll error:', e);
    }
  };

  const toggleAudio = () => {
    if (localStream) {
      localStream.getAudioTracks().forEach(t => t.enabled = !t.enabled);
      setAudioOn(!audioOn);
    }
  };

  const toggleVideo = () => {
    if (localStream) {
      localStream.getVideoTracks().forEach(t => t.enabled = !t.enabled);
      setVideoOn(!videoOn);
    }
  };

  const endCall = async () => {
    cleanup();
    try {
      await api.post(`/video/rooms/${roomId}/close`);
    } catch (e) {
      console.error('Failed to close room:', e);
    }
    navigate('/dashboard');
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white p-4" data-testid="video-call-page">
      <div className="max-w-6xl mx-auto">
        <div className="mb-4 flex justify-between items-center">
          <h1 className="text-xl font-semibold">{t('videoCall')}</h1>
          <span className="text-sm text-slate-400">{t(status)}</span>
        </div>

        <div className="grid md:grid-cols-2 gap-4 mb-6">
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-2 relative">
              <video ref={remoteVideoRef} autoPlay playsInline className="w-full aspect-video bg-black rounded" />
              {!connected && (
                <div className="absolute inset-0 flex items-center justify-center text-slate-400">
                  {t('waitingForPeer')}
                </div>
              )}
              <p className="text-xs mt-1">Remote</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-2">
              <video ref={localVideoRef} autoPlay playsInline muted className="w-full aspect-video bg-black rounded" />
              <p className="text-xs mt-1">You</p>
            </CardContent>
          </Card>
        </div>

        <div className="flex justify-center gap-3">
          <Button onClick={toggleAudio} variant={audioOn ? 'outline' : 'destructive'} size="lg" data-testid="toggle-audio-btn">
            {audioOn ? <Mic className="w-5 h-5" /> : <MicOff className="w-5 h-5" />}
          </Button>
          <Button onClick={toggleVideo} variant={videoOn ? 'outline' : 'destructive'} size="lg" data-testid="toggle-video-btn">
            {videoOn ? <Video className="w-5 h-5" /> : <VideoOff className="w-5 h-5" />}
          </Button>
          <Button onClick={endCall} variant="destructive" size="lg" data-testid="end-call-btn">
            <PhoneOff className="w-5 h-5 me-1" /> {t('endCall')}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default VideoCall;
