import React, { useState, useRef } from 'react';
import { useLanguage } from '../LanguageContext';
import { Button } from './ui/button';
import { Avatar, AvatarImage, AvatarFallback } from './ui/avatar';
import { Camera, Upload } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

const ProfilePictureUpload = ({ user, onUpdate }) => {
  const { t } = useLanguage();
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      toast.error('File too large (max 5MB)');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/upload?purpose=profile_picture', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success(t('uploadSuccess'));
      if (onUpdate) onUpdate(res.data.url);
    } catch (e) {
      toast.error(t('error'));
    } finally {
      setUploading(false);
    }
  };

  const token = localStorage.getItem('token');
  const imageUrl = user?.picture
    ? (user.picture.startsWith('/api') ? `${process.env.REACT_APP_BACKEND_URL}${user.picture}?auth=${token}` : user.picture)
    : null;

  const initials = user?.name?.split(' ').map(s => s[0]).join('').slice(0, 2).toUpperCase() || '?';

  return (
    <div className="flex items-center gap-4">
      <Avatar className="w-20 h-20 border-2 border-primary/20" data-testid="profile-avatar">
        {imageUrl && <AvatarImage src={imageUrl} alt={user?.name} />}
        <AvatarFallback className="bg-primary/10 text-primary text-xl font-semibold">{initials}</AvatarFallback>
      </Avatar>
      <div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          className="hidden"
          data-testid="profile-picture-input"
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          data-testid="upload-profile-btn"
        >
          {uploading ? (
            <>{t('uploadingFile')}</>
          ) : (
            <><Camera className="w-4 h-4 me-1" /> {t('uploadProfilePicture')}</>
          )}
        </Button>
      </div>
    </div>
  );
};

export default ProfilePictureUpload;
