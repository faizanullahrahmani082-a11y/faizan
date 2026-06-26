import React, { useState, useRef } from 'react';
import { useLanguage } from '../LanguageContext';
import { Avatar, AvatarImage, AvatarFallback } from './ui/avatar';
import { Camera } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const ProfilePictureUpload = ({ user, onUpdate, size = 'md' }) => {
  const { t } = useLanguage();
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error('File too large (max 5MB)'); return; }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/upload?purpose=profile_picture', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success(t('uploadSuccess'));
      if (onUpdate) onUpdate(res.data.url);
    } catch {
      toast.error(t('error'));
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const token = localStorage.getItem('token');
  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8000';
  const imageUrl = user?.picture
    ? (user.picture.startsWith('/api')
        ? `${backendUrl}${user.picture}?auth=${token}`
        : user.picture)
    : null;

  const initials = user?.name?.split(' ').map(s => s[0]).join('').slice(0, 2).toUpperCase() || '?';
  const dim = size === 'lg' ? 'w-16 h-16' : 'w-12 h-12';
  const textSize = size === 'lg' ? 'text-xl' : 'text-base';

  return (
    <div
      className={`relative group cursor-pointer shrink-0 ${uploading ? 'opacity-60' : ''}`}
      onClick={() => !uploading && fileInputRef.current?.click()}
      title={t('uploadProfilePicture')}
      data-testid="profile-avatar-wrapper"
    >
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        className="hidden"
        data-testid="profile-picture-input"
      />
      <Avatar className={`${dim} border-2 border-primary/20 transition-opacity`} data-testid="profile-avatar">
        {imageUrl && <AvatarImage src={imageUrl} alt={user?.name} />}
        <AvatarFallback className={`bg-primary/10 text-primary ${textSize} font-semibold`}>
          {initials}
        </AvatarFallback>
      </Avatar>
      {/* Camera overlay on hover */}
      <div className="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
        {uploading
          ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          : <Camera className="w-4 h-4 text-white" />
        }
      </div>
    </div>
  );
};

export default ProfilePictureUpload;
